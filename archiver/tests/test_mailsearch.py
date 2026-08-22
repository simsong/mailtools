"""Requirements: mailsearch is read-only and finds headers, text, and numbered mail."""

from __future__ import annotations

import hashlib
import mailbox
import subprocess
import sys
from os import environ
from pathlib import Path

from mailarchiver.catalog import address_pk, create_catalog, create_search
from mailarchiver.mailsearch import MessageHeader, format_header, render_message
from mailarchiver.mbox import add_message
from mailarchiver.search import index_message


def add_catalogued_message(archive: Path, message_pk: int, raw: bytes) -> None:
    path = archive / "2024-Archive1.mbox"
    box = mailbox.mbox(path, create=True)
    try:
        location = add_message(box, path, raw)
    finally:
        box.close()
    catalog = create_catalog(archive / "archive.sqlite3")
    try:
        generation = catalog.execute(
            "INSERT INTO mbox_generations(filename, sha256, message_count, byte_count) "
            "VALUES (?, '', 0, 0) ON CONFLICT(filename) DO UPDATE SET filename = excluded.filename "
            "RETURNING generation_pk",
            (path.name,),
        ).fetchone()
        assert generation is not None
        catalog.execute(
            "INSERT INTO locations(message_pk, generation_pk, byte_offset, byte_length) VALUES (?, ?, ?, ?)",
            (message_pk, generation[0], location.byte_offset, location.byte_length),
        )
        catalog.commit()
    finally:
        catalog.close()


def make_archive(tmp_path: Path) -> tuple[Path, bytes]:
    archive = tmp_path / "archive"
    archive.mkdir()
    raw = (
        b"Message-ID: <one@example>\nFrom: sender@example.net\nTo: recipient@example.net\nCc: copy@example.net\nX-Trace: one\n"
        b"Subject: planning meeting\nDate: Wed, 03 Jan 2024 10:00:00 +0000\n\nMeeting agenda.\n"
    )
    catalog = create_catalog(archive / "archive.sqlite3")
    search = create_search(archive / "search.sqlite3")
    try:
        sender, recipient = address_pk(catalog, "sender@example.net"), address_pk(catalog, "recipient@example.net")
        cursor = catalog.execute(
            "INSERT INTO messages(message_id_normalized, sha256, sender_address_pk, subject, date_utc, date_source, category) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("one@example", hashlib.sha256(raw).hexdigest(), sender, "planning meeting", "2024-01-03T10:00:00+00:00", "date", "Archive"),
        )
        message_pk = int(cursor.lastrowid)
        catalog.execute("INSERT INTO recipients(message_pk, address_pk) VALUES (?, ?)", (message_pk, recipient))
        catalog.commit()
        index_message(search, raw, False)
        search.commit()
    finally:
        catalog.close()
        search.close()
    add_catalogued_message(archive, message_pk, raw)
    return archive, raw


def run_search(*arguments: str, environment: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "mailarchiver.mailsearch", *arguments], capture_output=True, text=True, check=False, env=environment)


def test_mailsearch_finds_structured_and_full_text_matches(tmp_path: Path) -> None:
    """Requirement: selectors and ordinary terms intersect through the two databases."""
    archive, _ = make_archive(tmp_path)
    result = run_search(
        "--archive", str(archive), "to:recipient@example.net", "from:sender@example.net", "subject:planning", "date:2024-01-03", "agenda"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "1 to:recipient@example.net from:sender@example.net subject:planning meeting date:2024-01-03T10:00:00+00:00\n"


def test_mailsearch_limit_zero_and_number_print_original_message(tmp_path: Path) -> None:
    """Requirement: zero removes the result limit and a message number emits preserved RFC 5322 bytes."""
    archive, raw = make_archive(tmp_path)
    listed = run_search("--archive", str(archive), "--limit", "0")
    assert listed.returncode == 0, listed.stderr
    assert listed.stdout.startswith("1 to:recipient@example.net")
    displayed = subprocess.run(
        [sys.executable, "-m", "mailarchiver.mailsearch", "--archive", str(archive), "1"], capture_output=True, check=False
    )
    assert displayed.returncode == 0, displayed.stderr
    assert displayed.stdout == render_message(raw, False, False).encode()


def test_mailsearch_listing_excludes_quarantine_categories(tmp_path: Path) -> None:
    """Requirement: ordinary search results exclude catalogued quarantine mail."""
    archive, _ = make_archive(tmp_path)
    catalog = create_catalog(archive / "archive.sqlite3")
    try:
        sender = address_pk(catalog, "quarantine@example.net")
        for category in ("INFECTED", "MALFORMED"):
            catalog.execute(
                "INSERT INTO messages(message_id_normalized, sha256, sender_address_pk, subject, date_utc, date_source, category) "
                "VALUES (?, ?, ?, ?, '2024-01-04T10:00:00+00:00', 'date', ?)",
                (category.lower(), hashlib.sha256(category.encode()).hexdigest(), sender, category.lower(), category),
            )
        catalog.commit()
    finally:
        catalog.close()

    listed = run_search("--archive", str(archive), "--limit", "0")

    assert listed.returncode == 0, listed.stderr
    assert listed.stdout.count("\n") == 1
    assert "planning meeting" in listed.stdout
    assert "infected" not in listed.stdout
    assert "malformed" not in listed.stdout


def test_numbered_empty_message_restores_zero_source_bytes(tmp_path: Path) -> None:
    """Requirement: MBOX's separator newline does not change an empty message's identity."""
    archive = tmp_path / "archive"
    archive.mkdir()
    catalog = create_catalog(archive / "archive.sqlite3")
    search = create_search(archive / "search.sqlite3")
    try:
        blank = address_pk(catalog, "")
        cursor = catalog.execute(
            "INSERT INTO messages(message_id_normalized, sha256, sender_address_pk, subject, date_utc, date_source, category) "
            "VALUES (?, ?, ?, '', '2024-01-01T00:00:00+00:00', 'path-year', 'Archive')",
            (hashlib.sha256(b"").hexdigest(), hashlib.sha256(b"").hexdigest(), blank),
        )
        message_pk = int(cursor.lastrowid)
        catalog.commit()
    finally:
        catalog.close()
        search.close()
    add_catalogued_message(archive, message_pk, b"")

    displayed = subprocess.run(
        [sys.executable, "-m", "mailarchiver.mailsearch", "--archive", str(archive), "--mime", "1"],
        capture_output=True,
        check=False,
    )

    assert displayed.returncode == 0, displayed.stderr
    assert displayed.stdout == b""


def test_numbered_message_preserves_literal_quoted_from_line(tmp_path: Path) -> None:
    """Requirement: identity disambiguates an original >From line from MBOX quoting."""
    archive, _ = make_archive(tmp_path)
    raw = b"Message-ID: <quoted@example>\nDate: Thu, 1 Feb 2024 12:00:00 +0000\n\n>From original body\n"
    catalog = create_catalog(archive / "archive.sqlite3")
    try:
        blank = address_pk(catalog, "")
        cursor = catalog.execute(
            "INSERT INTO messages(message_id_normalized, sha256, sender_address_pk, subject, date_utc, date_source, category) "
            "VALUES ('quoted@example', ?, ?, '', '2024-01-01T00:00:00+00:00', 'date', 'Archive')",
            (hashlib.sha256(raw).hexdigest(), blank),
        )
        message_pk = int(cursor.lastrowid)
        catalog.commit()
    finally:
        catalog.close()
    add_catalogued_message(archive, message_pk, raw)

    displayed = subprocess.run(
        [sys.executable, "-m", "mailarchiver.mailsearch", "--archive", str(archive), "--mime", "2"],
        capture_output=True,
        check=False,
    )

    assert displayed.returncode == 0, displayed.stderr
    assert displayed.stdout == raw


def test_message_views_select_headers_and_preferred_mime_parts() -> None:
    """Requirement: display defaults to text/plain, supports HTML, and exposes full headers on request."""
    raw = (
        b"From: sender@example.net\nTo: recipient@example.net\nSubject: test\nX-Trace: retained\n"
        b"Content-Type: multipart/alternative; boundary=part\n\n--part\nContent-Type: text/plain; charset=utf-8\n\nPlain text\n"
        b"--part\nContent-Type: text/html; charset=utf-8\n\n<p>HTML text</p>\n--part--\n"
    )
    assert "Plain text" in render_message(raw, False, False)
    assert "HTML text" not in render_message(raw, False, False)
    assert "<p>HTML text</p>" in render_message(raw, False, True)
    assert "X-Trace: retained" in render_message(raw, True, False)
    html_only = raw.replace(b"Content-Type: text/plain; charset=utf-8\n\nPlain text\n", b"")
    assert "HTML text" in render_message(html_only, False, False)


def test_mailsearch_mime_outputs_original_source(tmp_path: Path) -> None:
    """Requirement: --mime returns all original MIME parts and headers unchanged."""
    archive, raw = make_archive(tmp_path)
    displayed = subprocess.run(
        [sys.executable, "-m", "mailarchiver.mailsearch", "--archive", str(archive), "--mime", "1"], capture_output=True, check=False
    )
    assert displayed.returncode == 0, displayed.stderr
    assert displayed.stdout == raw


def test_mailsearch_help_describes_syntax() -> None:
    """Requirement: help is sufficient to discover the search language and default limit."""
    result = run_search("--help")
    assert result.returncode == 0
    for selector in ("to:ADDRESS", "from:ADDRESS", "subject:TEXT", "date:YYYY-MM-DD", "before:YYYY-MM-DD", "after:YYYY-MM-DD"):
        assert selector in result.stdout
    assert "default: 10" in result.stdout
    assert max(map(len, result.stdout.splitlines())) <= 78


def test_mailsearch_date_bounds_are_strict_calendar_days(tmp_path: Path) -> None:
    """Requirement: date, before, and after use documented UTC calendar-day boundaries."""
    archive, _ = make_archive(tmp_path)
    assert run_search("--archive", str(archive), "before:2024-01-03").stdout == ""
    assert run_search("--archive", str(archive), "after:2024-01-03").stdout == ""
    assert run_search("--archive", str(archive), "after:2024-01-02").stdout.startswith("1 to:")


def test_mailsearch_formats_dynamic_numbers_and_terminal_subjects() -> None:
    """Requirement: numbers align to the result-set width and terminal subjects are bold."""
    header = MessageHeader(message_pk=42, recipients="to@example.net", sender="from@example.net", subject="subject", date_utc="2024-01-03T10:00:00+00:00")
    assert format_header(header, 4, False).startswith("  42 to:")
    assert "subject:\033[1msubject\033[0m" in format_header(header, 4, True)


def test_mail_archive_dir_defaults_and_archive_option_overrides(tmp_path: Path) -> None:
    """Requirement: both CLIs honor MAIL_ARCHIVE_DIR unless --archive supplies a different archive."""
    archive, _ = make_archive(tmp_path)
    environment = {**environ, "MAIL_ARCHIVE_DIR": str(archive)}
    assert run_search("subject:planning", environment=environment).stdout.startswith("1 to:")
    assert run_search("--archive", str(archive), "subject:planning", environment={**environ, "MAIL_ARCHIVE_DIR": str(tmp_path / "missing")}).stdout.startswith("1 to:")
    result = subprocess.run(
        [sys.executable, "-m", "mailarchiver", "report", "--top", "0"], capture_output=True, text=True, check=False, env=environment
    )
    assert result.returncode == 0, result.stderr
    override = subprocess.run(
        [sys.executable, "-m", "mailarchiver", "--archive", str(archive), "report", "--top", "0"],
        capture_output=True,
        text=True,
        check=False,
        env={**environ, "MAIL_ARCHIVE_DIR": str(tmp_path / "missing")},
    )
    assert override.returncode == 0, override.stderr
