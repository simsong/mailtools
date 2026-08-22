"""Typed read-only services for the graphical archive browser."""

from __future__ import annotations

import base64
import os
import re
import sqlite3
from email import policy
from email.message import Message
from email.parser import BytesParser
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from .mailsearch import MessageHeader, SortDirection, SortField, parse_query, read_message_bytes, search_headers
from .message import decoded_header
from .search import decoded_part, is_attachment

PAGE_SIZE = 100
RAW_PART_ID = -1
BLOCKED_ELEMENTS = {"base", "button", "embed", "form", "frame", "frameset", "iframe", "input", "link", "meta", "object", "script"}
RISKY_SUFFIXES = {
    ".app",
    ".applescript",
    ".bat",
    ".bin",
    ".command",
    ".dmg",
    ".exe",
    ".iso",
    ".jar",
    ".js",
    ".pkg",
    ".ps1",
    ".scpt",
    ".sh",
    ".vbs",
    ".zip",
}


class SearchPage(BaseModel):
    results: list[MessageHeader]
    offset: int
    has_more: bool


class MessagePreview(BaseModel):
    message_pk: int
    preview: str


class PreviewBatch(BaseModel):
    previews: list[MessagePreview]
    pending: bool
    error: str | None = None


class HeaderField(BaseModel):
    name: str
    value: str


class BodyPart(BaseModel):
    part_id: int
    content_type: str
    label: str


class AttachmentInfo(BaseModel):
    part_id: int
    filename: str
    content_type: str
    byte_length: int
    inline: bool
    preview: str | None = None
    risky: bool = False


class MessageView(BaseModel):
    message_pk: int
    subject: str
    headers: list[HeaderField]
    body_parts: list[BodyPart]
    preferred_part_id: int
    attachments: list[AttachmentInfo]


class PartContent(BaseModel):
    part_id: int
    kind: str
    content_type: str
    content: str
    remote_content_blocked: bool = False


class AttachmentContent(BaseModel):
    filename: str
    content_type: str
    content_base64: str


def search_page(
    archive: Path,
    query: str,
    offset: int = 0,
    limit: int = PAGE_SIZE,
    sort_by: SortField | str = SortField.DATE,
    direction: SortDirection | str = SortDirection.DESCENDING,
    search_attachments: bool = False,
) -> SearchPage:
    """Return one bounded page using exactly the CLI query language."""
    if offset < 0 or limit < 1:
        raise ValueError("search offset and limit must be positive")
    found = search_headers(
        archive,
        parse_query(query),
        limit + 1,
        offset,
        SortField(sort_by),
        SortDirection(direction),
        search_attachments,
    )
    return SearchPage(results=found[:limit], offset=offset, has_more=len(found) > limit)


def message_previews(archive: Path, message_pks: list[int]) -> list[MessagePreview]:
    """Read indexed body previews without opening canonical MBOX content."""
    unique_pks: list[int] = []
    seen: set[int] = set()
    for message_pk in message_pks:
        if message_pk not in seen:
            unique_pks.append(message_pk)
            seen.add(message_pk)
    if not unique_pks or len(unique_pks) > PAGE_SIZE:
        raise ValueError(f"request between 1 and {PAGE_SIZE} message previews")
    database = sqlite3.connect(f"file:{archive / 'archive.sqlite3'}?mode=ro", uri=True)
    try:
        database.execute("ATTACH DATABASE ? AS search", (f"file:{archive / 'search.sqlite3'}?mode=ro",))
        placeholders = ", ".join("?" for _ in unique_pks)
        rows = database.execute(
            "SELECT messages.message_pk, COALESCE(metadata.preview, '') FROM messages "
            "LEFT JOIN search.message_metadata metadata USING (sha256) "
            f"WHERE messages.message_pk IN ({placeholders})",
            unique_pks,
        )
        previews = {message_pk: preview for message_pk, preview in rows}
        return [MessagePreview(message_pk=message_pk, preview=previews.get(message_pk, "")) for message_pk in unique_pks]
    finally:
        database.close()


def parsed_message(archive: Path, message_pk: int) -> tuple[bytes, Message]:
    raw = read_message_bytes(archive, message_pk)
    return raw, BytesParser(policy=policy.compat32).parsebytes(raw)


def describe_message(archive: Path, message_pk: int) -> MessageView:
    """Describe selectable body parts and attachments without returning payloads."""
    _, message = parsed_message(archive, message_pk)
    headers = [HeaderField(name=name, value=decoded_header(str(value))) for name, value in message.items()]
    body_parts: list[BodyPart] = []
    attachments: list[AttachmentInfo] = []
    for part_id, part in enumerate(_parts(message)):
        content_type = part.get_content_type()
        attachment = _is_gui_attachment(part)
        if attachment:
            payload = _payload_bytes(part)
            filename = safe_filename(part.get_filename(), part_id, content_type)
            preview = "image" if content_type.startswith("image/") else "pdf" if content_type == "application/pdf" else None
            attachments.append(
                AttachmentInfo(
                    part_id=part_id,
                    filename=filename,
                    content_type=content_type,
                    byte_length=len(payload),
                    inline=part.get_content_disposition() == "inline" or bool(part.get("Content-ID")),
                    preview=preview,
                    risky=is_risky(filename, content_type),
                )
            )
        elif content_type in {"text/plain", "text/html"}:
            label = "Plain Text" if content_type == "text/plain" else "HTML"
            body_parts.append(BodyPart(part_id=part_id, content_type=content_type, label=f"{label} — part {part_id}"))
    body_parts.append(BodyPart(part_id=RAW_PART_ID, content_type="message/rfc822", label="Raw Source"))
    html_part = next((part.part_id for part in body_parts if part.content_type == "text/html"), None)
    text_part = next((part.part_id for part in body_parts if part.content_type == "text/plain"), RAW_PART_ID)
    return MessageView(
        message_pk=message_pk,
        subject=decoded_header(str(message.get("Subject", "(no subject)"))),
        headers=headers,
        body_parts=body_parts,
        preferred_part_id=html_part if html_part is not None else text_part,
        attachments=attachments,
    )


def render_part(archive: Path, message_pk: int, part_id: int, allow_remote: bool = False) -> PartContent:
    raw, message = parsed_message(archive, message_pk)
    if part_id == RAW_PART_ID:
        return PartContent(part_id=part_id, kind="raw", content_type="message/rfc822", content=raw.decode("utf-8", "replace"))
    part = _part(message, part_id)
    content_type = part.get_content_type()
    if content_type == "text/plain":
        return PartContent(part_id=part_id, kind="text", content_type=content_type, content=decoded_part(part))
    if content_type == "text/html":
        content, blocked = safe_html(decoded_part(part), message, allow_remote)
        return PartContent(
            part_id=part_id,
            kind="html",
            content_type=content_type,
            content=content,
            remote_content_blocked=blocked,
        )
    raise ValueError(f"MIME part {part_id} is not a displayable body part")


def attachment_content(archive: Path, message_pk: int, part_id: int) -> AttachmentContent:
    _, message = parsed_message(archive, message_pk)
    part = _part(message, part_id)
    content_type = part.get_content_type()
    filename = safe_filename(part.get_filename(), part_id, content_type)
    if not (is_attachment(part) or content_type.startswith("image/") or content_type == "application/pdf"):
        raise ValueError(f"MIME part {part_id} is not an attachment")
    return AttachmentContent(
        filename=filename,
        content_type=content_type,
        content_base64=base64.b64encode(_payload_bytes(part)).decode("ascii"),
    )


def write_message(archive: Path, message_pk: int, destination: Path) -> None:
    """Write an exact, verified RFC 5322 export outside the canonical archive."""
    _write_bytes(destination, read_message_bytes(archive, message_pk))


def write_attachment(archive: Path, message_pk: int, part_id: int, destination: Path) -> None:
    _, message = parsed_message(archive, message_pk)
    part = _part(message, part_id)
    if not (is_attachment(part) or part.get_content_type().startswith("image/") or part.get_content_type() == "application/pdf"):
        raise ValueError(f"MIME part {part_id} is not an attachment")
    _write_bytes(destination, _payload_bytes(part))


def export_filename(view: MessageView) -> str:
    subject = re.sub(r"[^\w .()-]+", "_", view.subject, flags=re.UNICODE).strip(" .") or "message"
    return f"{subject[:80]}-{view.message_pk}.eml"


def safe_filename(filename: str | None, part_id: int, content_type: str) -> str:
    candidate = Path(str(filename or "")).name
    candidate = "".join(character for character in candidate if character >= " " and character not in "/\\:")
    if candidate:
        return candidate
    suffix = ".pdf" if content_type == "application/pdf" else ".bin"
    if content_type.startswith("image/"):
        suffix = "." + content_type.split("/", 1)[1].replace("jpeg", "jpg")
    return f"attachment-{part_id}{suffix}"


def is_risky(filename: str, content_type: str) -> bool:
    return Path(filename).suffix.casefold() in RISKY_SUFFIXES or content_type in {
        "application/java-archive",
        "application/vnd.apple.installer+xml",
        "application/x-executable",
        "application/x-mach-binary",
        "application/x-sh",
    }


def safe_html(value: str, message: Message, allow_remote: bool) -> tuple[str, bool]:
    """Return inert HTML with CID images resolved and remote loads policy-controlled."""
    soup = BeautifulSoup(value, "html.parser")
    for element in soup.find_all(tuple(BLOCKED_ELEMENTS)):
        element.decompose()
    cid_images = _cid_images(message)
    remote_blocked = False
    for element in soup.find_all(True):
        for attribute in list(element.attrs):
            if attribute.casefold().startswith("on") or attribute.casefold() in {"srcset", "formaction", "poster"}:
                del element.attrs[attribute]
        if element.name == "a" and element.get("href"):
            href = str(element["href"])
            if urlparse(href).scheme.casefold() not in {"http", "https", "mailto"}:
                del element.attrs["href"]
            else:
                element["target"], element["rel"] = "_blank", "noopener noreferrer"
        if element.name == "img" and element.get("src"):
            source = str(element["src"])
            if source.casefold().startswith("cid:"):
                replacement = cid_images.get(source[4:].strip("<>").casefold())
                if replacement:
                    element["src"] = replacement
                else:
                    del element.attrs["src"]
            elif urlparse(source).scheme.casefold() in {"http", "https"}:
                if not allow_remote:
                    del element.attrs["src"]
                    remote_blocked = True
            elif not source.casefold().startswith("data:image/"):
                del element.attrs["src"]
    image_sources = "data: http: https:" if allow_remote else "data:"
    csp = soup.new_tag("meta")
    csp["http-equiv"] = "Content-Security-Policy"
    csp["content"] = f"default-src 'none'; img-src {image_sources}; style-src 'unsafe-inline'; font-src 'none'; media-src 'none'"
    if soup.head:
        soup.head.insert(0, csp)
    else:
        soup.insert(0, csp)
    return str(soup), remote_blocked


def _parts(message: Message) -> list[Message]:
    return list(message.walk()) if message.is_multipart() else [message]


def _is_gui_attachment(part: Message) -> bool:
    content_type = part.get_content_type()
    return is_attachment(part) or content_type.startswith("image/") or content_type == "application/pdf"


def _part(message: Message, part_id: int) -> Message:
    parts = _parts(message)
    if part_id < 0 or part_id >= len(parts):
        raise ValueError(f"no MIME part {part_id}")
    return parts[part_id]


def _payload_bytes(part: Message) -> bytes:
    payload = part.get_payload(decode=True)
    if isinstance(payload, bytes):
        return payload
    value = part.get_payload()
    if isinstance(value, str):
        return value.encode(part.get_content_charset() or "utf-8", "replace")
    return b""


def _cid_images(message: Message) -> dict[str, str]:
    images: dict[str, str] = {}
    for part in _parts(message):
        content_id = str(part.get("Content-ID", "")).strip("<>").casefold()
        if content_id and part.get_content_type().startswith("image/"):
            encoded = base64.b64encode(_payload_bytes(part)).decode("ascii")
            images[content_id] = f"data:{part.get_content_type()};base64,{encoded}"
    return images


def _write_bytes(destination: Path, value: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as output:
            output.write(value)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
