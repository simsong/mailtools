"""Disposable FTS5 indexing of message text, never raw MIME attachments."""

from __future__ import annotations

import hashlib
import sqlite3
import warnings
from email import policy
from email.message import Message
from email.parser import BytesParser

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from .message import decoded_header

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


def message_text(raw: bytes, index_attachments: bool) -> str:
    """Return headers plus preferred body text; omit attachments unless requested."""
    message = BytesParser(policy=policy.compat32).parsebytes(raw)
    headers = "\n".join(decoded_header(str(message.get(name) or "")) for name in ("From", "To", "Cc", "Subject", "Date"))
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
    if index_attachments:
        attachments = [decoded_part(part) for part in parts if is_attachment(part) and part.get_content_maintype() == "text"]
        body = "\n".join([body, *attachments])
    return "\n".join((headers, body))


def index_message(search: sqlite3.Connection, raw: bytes, index_attachments: bool) -> None:
    search.execute("INSERT INTO message_fts(sha256, content) VALUES (?, ?)", (hashlib.sha256(raw).hexdigest(), message_text(raw, index_attachments)))
