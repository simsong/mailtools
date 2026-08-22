"""Disposable FTS5 indexing of message text, never raw MIME attachments."""

from __future__ import annotations

import hashlib
import re
import sqlite3
import warnings
from email import policy
from email.message import Message
from email.parser import BytesParser

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from pydantic import BaseModel

from .message import decoded_header

SEARCH_CATEGORIES = ("Archive", "Sent")
QUARANTINE_MAILBOX = re.compile(r"^(?:INFECTED|MALFORMED)\d+\.mbox$")
PREVIEW_WORDS = 18


class IndexedAttachment(BaseModel):
    attachment_ordinal: int
    part_id: int
    filename: str
    mime_type: str


def decoded_part(part: Message) -> str:
    payload = part.get_payload(decode=True) or b""
    try:
        return payload.decode(part.get_content_charset() or "utf-8", "replace")
    except LookupError:
        return payload.decode("utf-8", "replace")


def is_attachment(part: Message) -> bool:
    return part.get_content_disposition() == "attachment" or part.get_filename() is not None


def html_text(value: str) -> str:
    """Render email HTML, including XML-looking XHTML declared as text/html."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        return BeautifulSoup(value, "html.parser").get_text(" ", strip=True)


def preferred_body_text(message: Message) -> str:
    """Extract the user-readable message body without attachment text."""
    parts = list(message.walk()) if message.is_multipart() else [message]
    plain = [decoded_part(part) for part in parts if part.get_content_type() == "text/plain" and not is_attachment(part)]
    html = [decoded_part(part) for part in parts if part.get_content_type() == "text/html" and not is_attachment(part)]
    if plain:
        body = "\n".join(plain)
    elif html:
        body = "\n".join(html_text(part) for part in html)
    elif not message.is_multipart() and not is_attachment(message):
        body = decoded_part(message)
    else:
        body = ""
    return body


def parsed_message_text(message: Message, index_attachments: bool, body: str | None = None) -> str:
    headers = "\n".join(decoded_header(str(message.get(name) or "")) for name in ("From", "To", "Cc", "Subject", "Date"))
    parts = list(message.walk()) if message.is_multipart() else [message]
    body = preferred_body_text(message) if body is None else body
    if index_attachments:
        attachments = [decoded_part(part) for part in parts if is_attachment(part) and part.get_content_maintype() == "text"]
        body = "\n".join([body, *attachments])
    return "\n".join((headers, body))


def attachment_text(message: Message) -> str:
    """Return decoded text from MIME attachments, excluding binary payloads."""
    parts = list(message.walk()) if message.is_multipart() else [message]
    return "\n".join(
        decoded_part(part) for part in parts if is_attachment(part) and part.get_content_maintype() == "text"
    )


def body_preview(body: str, word_limit: int = PREVIEW_WORDS) -> str:
    """Collapse the first bounded body words into a single display line."""
    words = re.findall(r"\S+", body)
    return " ".join(words[:word_limit]) + ("…" if len(words) > word_limit else "")


def message_text(raw: bytes, index_attachments: bool) -> str:
    """Return headers plus preferred body text; omit attachments unless requested."""
    message = BytesParser(policy=policy.compat32).parsebytes(raw)
    return parsed_message_text(message, index_attachments)


def indexed_attachments(message: Message) -> list[IndexedAttachment]:
    """Return stable metadata for MIME parts treated as attachments."""
    parts = list(message.walk()) if message.is_multipart() else [message]
    attachments: list[IndexedAttachment] = []
    for part_id, part in enumerate(parts):
        if not is_attachment(part):
            continue
        ordinal = len(attachments) + 1
        supplied_name = part.get_filename()
        filename = decoded_header(str(supplied_name)).strip() if supplied_name is not None else f"attachment-{ordinal}"
        attachments.append(
            IndexedAttachment(
                attachment_ordinal=ordinal,
                part_id=part_id,
                filename=filename or f"attachment-{ordinal}",
                mime_type=part.get_content_type(),
            )
        )
    return attachments


def index_message(search: sqlite3.Connection, raw: bytes, index_attachments: bool) -> None:
    digest = hashlib.sha256(raw).hexdigest()
    message = BytesParser(policy=policy.compat32).parsebytes(raw)
    attachments = indexed_attachments(message)
    body = preferred_body_text(message)
    search.execute("DELETE FROM message_fts WHERE sha256 = ?", (digest,))
    search.execute("DELETE FROM attachment_fts WHERE sha256 = ?", (digest,))
    search.execute("INSERT INTO message_fts(sha256, content) VALUES (?, ?)", (digest, parsed_message_text(message, False, body)))
    if index_attachments and (attachments_text := attachment_text(message)):
        search.execute("INSERT INTO attachment_fts(sha256, content) VALUES (?, ?)", (digest, attachments_text))
    search.execute(
        "INSERT INTO message_metadata(sha256, attachment_count, preview) VALUES (?, ?, ?) "
        "ON CONFLICT(sha256) DO UPDATE SET attachment_count = excluded.attachment_count, preview = excluded.preview",
        (digest, len(attachments), body_preview(body)),
    )
    search.execute("DELETE FROM message_attachments WHERE sha256 = ?", (digest,))
    search.executemany(
        "INSERT INTO message_attachments(sha256, attachment_ordinal, part_id, filename, mime_type) VALUES (?, ?, ?, ?, ?)",
        ((digest, item.attachment_ordinal, item.part_id, item.filename, item.mime_type) for item in attachments),
    )


def index_message_safely(
    catalog: sqlite3.Connection, search: sqlite3.Connection, message_pk: int, raw: bytes, index_attachments: bool
) -> None:
    """Index disposable content without allowing extraction failure to veto canonical mail."""
    try:
        index_message(search, raw, index_attachments)
        search.commit()
    except Exception as error:
        search.rollback()
        catalog.execute(
            "INSERT OR IGNORE INTO metadata_defects(message_pk, field, detail) VALUES (?, 'search-index', ?)",
            (message_pk, f"{type(error).__name__}: {error}"),
        )
        catalog.commit()
