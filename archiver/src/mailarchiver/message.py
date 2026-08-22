"""Raw-message metadata parsing and date resolution."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from email.header import decode_header
from email.message import Message
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


YEAR = re.compile(r"^(19|20)\d{2}$")
GOOGLE_CHAT_SENDER = re.compile(
    r'^sender\s*\{.*?^\s*full_name:\s*"((?:[^"\\]|\\.)*)".*?^\}\s*$',
    re.MULTILINE | re.DOTALL,
)
EMBEDDED_MBOX_ENVELOPE = re.compile(br"(?m)^>From [^\r\n]*\r?\n")


class MetadataDefect(BaseModel):
    field: str
    detail: str


class ParsedMessage(BaseModel):
    message_id: str
    sha256: str
    sender: str
    recipients: list[str]
    subject: str
    date_utc: str
    date_source: str
    autosave: bool
    defects: list[MetadataDefect] = Field(default_factory=list)


class DecodedHeaderValue(BaseModel):
    value: str
    defect: str | None = None


class SenderIdentity(BaseModel):
    value: str
    source: Literal["from", "embedded-from", "sender", "google-chat", "missing"]


def parse_date(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except Exception:
        return None
    if parsed is None or not 1900 <= parsed.year <= datetime.now(timezone.utc).year + 1:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def path_year(path: Path) -> int | None:
    for part in reversed(path.parts):
        if YEAR.fullmatch(part):
            return int(part)
    return None


def received_date(values: list[object]) -> datetime | None:
    dates = [parsed for value in values if (parsed := parse_date(str(value).rsplit(";", 1)[-1].strip())) is not None]
    return min(dates) if dates else None


def decode_header_value(value: str) -> DecodedHeaderValue:
    """Decode RFC 2047 encoded words without letting malformed metadata drop mail."""
    unfolded = re.sub(r"\r?\n[ \t]+", " ", value)
    try:
        parts = decode_header(unfolded)
    except Exception as error:
        return DecodedHeaderValue(value=unfolded, defect=f"{type(error).__name__}: {error}")
    decoded: list[str] = []
    defect: str | None = None
    for part, charset in parts:
        if isinstance(part, str):
            decoded.append(part)
            continue
        try:
            decoded.append(part.decode(charset or "utf-8", "replace"))
        except (LookupError, UnicodeError) as error:
            decoded.append(part.decode("utf-8", "replace"))
            defect = f"{type(error).__name__}: {error}"
    return DecodedHeaderValue(value="".join(decoded), defect=defect)


def decoded_header(value: str) -> str:
    return decode_header_value(value).value


def header_values(message: Message, name: str, defects: list[MetadataDefect]) -> list[str]:
    try:
        return [str(value) for value in message.get_all(name, [])]
    except Exception as error:
        defects.append(MetadataDefect(field=name, detail=f"{type(error).__name__}: {error}"))
        return []


def sender_identity(message: Message, defects: list[MetadataDefect], raw: bytes | None = None) -> SenderIdentity:
    """Resolve an email sender or a narrowly identified Google Chat actor."""
    from_values = header_values(message, "From", defects)
    try:
        address = parseaddr(from_values[0] if from_values else "")[1].lower()
    except Exception as error:
        defects.append(MetadataDefect(field="From", detail=f"{type(error).__name__}: {error}"))
        address = ""
    if address:
        return SenderIdentity(value=address, source="from")

    if raw is not None and (match := EMBEDDED_MBOX_ENVELOPE.search(raw)) is not None:
        header_end = raw.find(b"\n\n")
        if header_end < 0 or match.start() < header_end:
            embedded = BytesParser(policy=policy.compat32).parsebytes(raw[match.end():])
            embedded_values = header_values(embedded, "From", defects)
            try:
                address = parseaddr(embedded_values[0] if embedded_values else "")[1].lower()
            except Exception as error:
                defects.append(MetadataDefect(field="From", detail=f"{type(error).__name__}: {error}"))
                address = ""
            if address:
                defects.append(MetadataDefect(field="From", detail="used quoted embedded MBOX From header"))
                return SenderIdentity(value=address, source="embedded-from")

    sender_values = header_values(message, "Sender", defects)
    try:
        address = parseaddr(sender_values[0] if sender_values else "")[1].lower()
    except Exception as error:
        defects.append(MetadataDefect(field="Sender", detail=f"{type(error).__name__}: {error}"))
        address = ""
    if address:
        defects.append(MetadataDefect(field="From", detail="missing or invalid; used Sender header"))
        return SenderIdentity(value=address, source="sender")

    if message.get("X-GM-THRID") is not None and not message.is_multipart():
        payload = message.get_payload(decode=True)
        text = payload.decode("utf-8", "replace") if isinstance(payload, bytes) else str(message.get_payload())
        if "conversation_id:" in text and "event_id:" in text and (match := GOOGLE_CHAT_SENDER.search(text)):
            name = match.group(1).replace(r'\"', '"').replace(r"\\", "\\")
            defects.append(MetadataDefect(field="From", detail="missing; used Google Chat body identity"))
            return SenderIdentity(value=f"{name} (Google Chat)", source="google-chat")

    defects.append(MetadataDefect(field="From", detail="missing or invalid sender address"))
    return SenderIdentity(value="", source="missing")


def parse_message(raw: bytes, path: Path, prior_date: datetime | None) -> ParsedMessage:
    message = BytesParser(policy=policy.compat32).parsebytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    defects: list[MetadataDefect] = []
    message_id_values = header_values(message, "Message-ID", defects)
    message_id = (message_id_values[0] if message_id_values else "").strip().strip("<>").lower() or digest
    sender = sender_identity(message, defects, raw).value
    recipient_headers = [value for name in ("To", "Cc", "Bcc") for value in header_values(message, name, defects)]
    try:
        recipients = sorted({address.lower() for _, address in getaddresses(recipient_headers) if address})
    except Exception as error:
        defects.append(MetadataDefect(field="recipients", detail=f"{type(error).__name__}: {error}"))
        recipients = []
    date_values = header_values(message, "Date", defects)
    date_value = date_values[0] if date_values else None
    date = parse_date(date_value)
    if date_value is not None and date is None:
        defects.append(MetadataDefect(field="Date", detail="invalid or implausible date"))
    if date is not None:
        date_source = "date"
    elif (date := received_date(header_values(message, "Received", defects))) is not None:
        date_source = "received"
    elif prior_date is not None:
        date, date_source = prior_date, "previous-message"
    else:
        year = path_year(path)
        if year is None:
            raise ValueError(f"no date or year path fallback for {path}")
        date, date_source = datetime(year, 1, 1, tzinfo=timezone.utc), "path-year"
    subject_values = header_values(message, "Subject", defects)
    subject = decode_header_value(subject_values[0] if subject_values else "")
    if subject.defect is not None:
        defects.append(MetadataDefect(field="Subject", detail=subject.defect))
    autosave = bool(header_values(message, "X-Apple-Auto-Saved", defects))
    return ParsedMessage(
        message_id=message_id,
        sha256=digest,
        sender=sender,
        recipients=recipients,
        subject=subject.value,
        date_utc=date.isoformat(),
        date_source=date_source,
        autosave=autosave,
        defects=defects,
    )
