"""Read-only Apple Mail-style search over a mailarchiver archive."""

from __future__ import annotations

import argparse
import hashlib
import shlex
import shutil
import sqlite3
import sys
import textwrap
from datetime import date as CalendarDate, timedelta
from email import policy
from email.message import Message
from email.parser import BytesParser
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from .archive_path import add_archive_argument, require_archive
from .message import decoded_header
from .mbox import MboxLocation, read_verified_location
from .search import SEARCH_CATEGORIES, decoded_part, html_text, is_attachment

DEFAULT_LIMIT = 10
BOLD = "\033[1m"
RESET = "\033[0m"


class SearchTerms(BaseModel):
    """Structured selectors and free-text terms accepted by mailsearch."""

    to: list[str] = Field(default_factory=list)
    from_: list[str] = Field(default_factory=list)
    subject: list[str] = Field(default_factory=list)
    date: list[CalendarDate] = Field(default_factory=list)
    before: list[CalendarDate] = Field(default_factory=list)
    after: list[CalendarDate] = Field(default_factory=list)
    text: list[str] = Field(default_factory=list)


class MessageHeader(BaseModel):
    message_pk: int
    recipients: str
    sender: str
    subject: str
    date_utc: str
    attachment_count: int = 0


class SortField(StrEnum):
    DATE = "date"
    SUBJECT = "subject"
    SENDER = "sender"


class SortDirection(StrEnum):
    ASCENDING = "ascending"
    DESCENDING = "descending"


def parse_terms(tokens: list[str]) -> SearchTerms:
    terms = SearchTerms()
    for token in tokens:
        key, separator, value = token.partition(":")
        key = key.lower()
        if separator and key in {"to", "from", "subject", "date", "before", "after"}:
            if not value:
                raise ValueError(f"{key}: requires a value")
            if key in {"date", "before", "after"}:
                try:
                    getattr(terms, key).append(CalendarDate.fromisoformat(value))
                except ValueError as error:
                    raise ValueError(f"{key}: requires a YYYY-MM-DD date") from error
            else:
                getattr(terms, "from_" if key == "from" else key).append(value.casefold())
        else:
            terms.text.append(token)
    return terms


def fts_query(words: list[str]) -> str:
    return " AND ".join(f'"{word.replace(chr(34), "")}"' for word in words)


def contains(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def parse_query(query: str) -> SearchTerms:
    """Parse one GUI-style search field with shell-compatible quoting."""
    try:
        return parse_terms(shlex.split(query))
    except ValueError as error:
        if "No closing quotation" in str(error):
            raise ValueError("search has an unclosed quote") from error
        raise


def search_headers(
    archive: Path,
    terms: SearchTerms,
    limit: int,
    offset: int = 0,
    sort_by: SortField = SortField.DATE,
    direction: SortDirection = SortDirection.DESCENDING,
    search_attachments: bool = False,
) -> list[MessageHeader]:
    catalog_path, search_path = archive / "archive.sqlite3", archive / "search.sqlite3"
    if not catalog_path.is_file() or not search_path.is_file():
        raise ValueError(f"{archive} must contain archive.sqlite3 and search.sqlite3")
    database = sqlite3.connect(f"file:{catalog_path}?mode=ro", uri=True)
    try:
        database.execute("ATTACH DATABASE ? AS search", (f"file:{search_path}?mode=ro",))
        clauses = ["m.category IN (?, ?)"]
        parameters: list[str | int] = list(SEARCH_CATEGORIES)
        for address in terms.to:
            clauses.append(
                "EXISTS (SELECT 1 FROM recipients r JOIN email_addresses a ON a.address_pk = r.address_pk "
                "WHERE r.message_pk = m.message_pk AND lower(a.address) LIKE ? ESCAPE '\\')"
            )
            parameters.append(contains(address))
        for address in terms.from_:
            clauses.append("lower(sender.address) LIKE ? ESCAPE '\\'")
            parameters.append(contains(address))
        for subject in terms.subject:
            clauses.append("lower(m.subject) LIKE ? ESCAPE '\\'")
            parameters.append(contains(subject))
        for selected_date in terms.date:
            clauses.append("m.date_utc >= ? AND m.date_utc < ?")
            parameters.extend((selected_date.isoformat() + "T00:00:00+00:00", (selected_date + timedelta(days=1)).isoformat() + "T00:00:00+00:00"))
        for selected_date in terms.before:
            clauses.append("m.date_utc < ?")
            parameters.append(selected_date.isoformat() + "T00:00:00+00:00")
        for selected_date in terms.after:
            clauses.append("m.date_utc >= ?")
            parameters.append((selected_date + timedelta(days=1)).isoformat() + "T00:00:00+00:00")
        if terms.text:
            if search_attachments:
                for term in terms.text:
                    clauses.append(
                        "m.sha256 IN (SELECT sha256 FROM search.message_fts WHERE message_fts MATCH ? "
                        "UNION SELECT sha256 FROM search.attachment_fts WHERE attachment_fts MATCH ?)"
                    )
                    match = fts_query([term])
                    parameters.extend((match, match))
            else:
                clauses.append("m.sha256 IN (SELECT sha256 FROM search.message_fts WHERE message_fts MATCH ?)")
                parameters.append(fts_query(terms.text))
        order_column = {
            SortField.DATE: "m.date_utc",
            SortField.SUBJECT: "lower(m.subject)",
            SortField.SENDER: "lower(sender.address)",
        }[sort_by]
        order_direction = "ASC" if direction == SortDirection.ASCENDING else "DESC"
        query = (
            "SELECT m.message_pk, COALESCE(group_concat(DISTINCT recipient.address), ''), sender.address, m.subject, m.date_utc, "
            "COALESCE(metadata.attachment_count, 0) "
            "FROM messages m JOIN email_addresses sender ON sender.address_pk = m.sender_address_pk "
            "LEFT JOIN search.message_metadata metadata ON metadata.sha256 = m.sha256 "
            "LEFT JOIN recipients r ON r.message_pk = m.message_pk "
            "LEFT JOIN email_addresses recipient ON recipient.address_pk = r.address_pk "
            + ("WHERE " + " AND ".join(clauses) + " " if clauses else "")
            + f"GROUP BY m.message_pk ORDER BY {order_column} {order_direction}, m.message_pk {order_direction} "
            + ("" if limit == 0 else "LIMIT ? OFFSET ?")
        )
        if limit:
            parameters.extend((limit, offset))
        fields = ("message_pk", "recipients", "sender", "subject", "date_utc", "attachment_count")
        return [MessageHeader.model_validate(dict(zip(fields, row))) for row in database.execute(query, parameters)]
    finally:
        database.close()


def rendered_headers(message: Message, full: bool) -> str:
    headers = message.items() if full else [(name, message.get(name)) for name in ("To", "From", "Cc", "Subject", "Date")]
    return "\n".join(f"{name}: {decoded_header(str(value))}" for name, value in headers if value is not None)


def text_parts(message: Message, content_type: str) -> list[str]:
    parts = message.walk() if message.is_multipart() else [message]
    return [decoded_part(part) for part in parts if part.get_content_type() == content_type and not is_attachment(part)]


def render_message(raw: bytes, full_headers: bool, html: bool) -> str:
    """Render selected headers and a user-readable preferred message part."""
    message = BytesParser(policy=policy.compat32).parsebytes(raw)
    headers = rendered_headers(message, full_headers)
    plain = text_parts(message, "text/plain")
    html_parts = text_parts(message, "text/html")
    if html:
        body = "\n\n".join(html_parts)
    elif plain:
        body = "\n\n".join(plain)
    else:
        body = "\n\n".join(html_text(part) for part in html_parts)
    return headers + ("\n\n" + body.rstrip("\n") if body else "") + "\n"


def read_message_bytes(archive: Path, message_pk: int) -> bytes:
    """Return one canonical message after direct-location SHA-256 validation."""
    database = sqlite3.connect(f"file:{archive / 'archive.sqlite3'}?mode=ro", uri=True)
    try:
        row = database.execute(
            "SELECT messages.sha256, mbox_generations.filename, locations.byte_offset, locations.byte_length "
            "FROM messages LEFT JOIN locations USING (message_pk) "
            "LEFT JOIN mbox_generations USING (generation_pk) WHERE message_pk = ?",
            (message_pk,),
        ).fetchone()
    finally:
        database.close()
    if row is None:
        raise ValueError(f"no message numbered {message_pk}")
    target, filename, offset, length = row
    if filename is None:
        raise ValueError(f"archive invariant failed: message {message_pk} has no MBOX location")
    try:
        raw = read_verified_location(
            archive / filename,
            MboxLocation(byte_offset=offset, byte_length=length),
            target,
        )
    except ValueError as error:
        raise ValueError(f"MBOX location hash mismatch for message {message_pk}") from error
    return raw


def print_message(archive: Path, message_pk: int, full_headers: bool, html: bool, mime: bool) -> None:
    raw = read_message_bytes(archive, message_pk)
    if mime:
        sys.stdout.buffer.write(raw)
    else:
        sys.stdout.write(render_message(raw, full_headers, html))


def format_header(result: MessageHeader, number_width: int, styled: bool) -> str:
    """Format a one-line result, emphasizing the subject only for terminals."""
    subject = result.subject
    if styled:
        subject = f"{BOLD}{subject}{RESET}"
    return f"{result.message_pk:>{number_width}} to:{result.recipients} from:{result.sender} subject:{subject} date:{result.date_utc}"


def terminal_width() -> int:
    return max(40, shutil.get_terminal_size(fallback=(80, 24)).columns - 2)


def search_epilog() -> str:
    width = terminal_width()
    selectors = (
        ("to:ADDRESS", "recipient address"),
        ("from:ADDRESS", "sender address"),
        ("subject:TEXT", "subject text"),
        ("date:YYYY-MM-DD", "messages on that UTC calendar day"),
        ("before:YYYY-MM-DD", "messages before that UTC calendar day"),
        ("after:YYYY-MM-DD", "messages after that UTC calendar day"),
    )
    selector_lines = [textwrap.fill(f"  {key:<21} {description}", width=width, subsequent_indent=" " * 23) for key, description in selectors]
    examples = (
        "  mailsearch to:alice@example.com budget",
        "  mailsearch --limit 0 after:2024-01-01",
        "  mailsearch --archive OTHER_ARCHIVE 42",
    )
    return "\n\n".join(
        (
            textwrap.fill("Ordinary words search indexed headers and message text. Every term is ANDed.", width=width),
            "Search selectors:\n" + "\n".join(selector_lines),
            textwrap.fill("A sole message number prints selected headers and the preferred text part. Use --headers, --html, or --mime for alternate views.", width=width),
            "Examples:\n" + "\n".join(examples),
        )
    )


class TerminalHelpFormatter(argparse.HelpFormatter):
    """Wrap help to the current terminal width, including the search syntax."""

    def __init__(self, prog: str) -> None:
        super().__init__(prog, width=terminal_width())

    def _fill_text(self, text: str, width: int, indent: str) -> str:
        return "\n".join(indent + line for line in text.splitlines())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mailsearch",
        description="Read-only search of a mailarchiver archive.",
        epilog=search_epilog(),
        formatter_class=TerminalHelpFormatter,
    )
    add_archive_argument(parser, "directory containing archive.sqlite3 and search.sqlite3")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="maximum matches to print; 0 prints all (default: 10)")
    parser.add_argument("--headers", action="store_true", help="with a message number, show all headers")
    view = parser.add_mutually_exclusive_group()
    view.add_argument("--html", action="store_true", help="with a message number, print decoded text/html parts")
    view.add_argument("--mime", action="store_true", help="with a message number, print the full RFC 5322/MIME source")
    parser.add_argument("terms", nargs="*", metavar="SEARCH")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.archive = require_archive(parser, args.archive)
    if args.limit < 0:
        raise SystemExit("mailsearch: --limit must be zero or positive")
    try:
        if len(args.terms) == 1 and args.terms[0].isdigit():
            print_message(args.archive, int(args.terms[0]), args.headers, args.html, args.mime)
            return 0
        terms = parse_terms(args.terms)
        results = search_headers(args.archive, terms, args.limit)
        number_width = max((len(str(result.message_pk)) for result in results), default=1)
        for result in results:
            print(format_header(result, number_width, sys.stdout.isatty()))
    except ValueError as error:
        raise SystemExit(f"mailsearch: {error}") from error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
