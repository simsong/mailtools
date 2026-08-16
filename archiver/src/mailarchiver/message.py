"""Raw-message metadata parsing and date resolution."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from pathlib import Path

from pydantic import BaseModel


YEAR = re.compile(r"^(19|20)\d{2}$")


class ParsedMessage(BaseModel):
    message_id: str
    sha256: str
    sender: str
    recipients: list[str]
    subject: str
    date_utc: str
    date_source: str
    autosave: bool


def parse_date(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if parsed is None:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def path_year(path: Path) -> int | None:
    for part in reversed(path.parts):
        if YEAR.fullmatch(part):
            return int(part)
    return None


def received_date(values: list[str]) -> datetime | None:
    dates = [parsed for value in values if (parsed := parse_date(value.rsplit(";", 1)[-1].strip())) is not None]
    return min(dates) if dates else None


def parse_message(raw: bytes, path: Path, prior_date: datetime | None) -> ParsedMessage:
    message = BytesParser(policy=policy.compat32).parsebytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    message_id = str(message.get("Message-ID") or "").strip().strip("<>").lower() or digest
    sender = parseaddr(str(message.get("From") or ""))[1].lower()
    recipients = sorted(
        {address.lower() for _, address in getaddresses(message.get_all("To", []) + message.get_all("Cc", []) + message.get_all("Bcc", [])) if address}
    )
    date = parse_date(str(message.get("Date")) if message.get("Date") else None)
    if date is not None:
        date_source = "date"
    elif (date := received_date(message.get_all("Received", []))) is not None:
        date_source = "received"
    elif prior_date is not None:
        date, date_source = prior_date, "previous-message"
    else:
        year = path_year(path)
        if year is None:
            raise ValueError(f"no date or year path fallback for {path}")
        date, date_source = datetime(year, 1, 1, tzinfo=timezone.utc), "path-year"
    return ParsedMessage(
        message_id=message_id,
        sha256=digest,
        sender=sender,
        recipients=recipients,
        subject=str(message.get("Subject") or ""),
        date_utc=date.isoformat(),
        date_source=date_source,
        autosave=message.get("X-Apple-Auto-Saved") is not None,
    )
