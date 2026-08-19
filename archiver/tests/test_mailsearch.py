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
from mailarchiver.search import index_message


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
        catalog.execute("INSERT INTO recipients(message_pk, address_pk) VALUES (?, ?)", (cursor.lastrowid, recipient))
        catalog.commit()
        index_message(search, raw, False)
        search.commit()
    finally:
        catalog.close()
        search.close()
    box = mailbox.mbox(archive / "2024-Archive1.mbox")
    try:
        box.add(raw)
        box.flush()
    finally:
        box.close()
    refreshed = subprocess.run(
        [sys.executable, "-m", "mailarchiver", "--archive", str(archive), "refresh-locations"], capture_output=True, text=True, check=False
    )
    assert refreshed.returncode == 0, refreshed.stderr
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


def test_refresh_locations_rebuilds_direct_numbered_lookup(tmp_path: Path) -> None:
    """Requirement: a rebuilt location maps a message number directly to preserved RFC 5322 bytes."""
    archive, raw = make_archive(tmp_path)
    catalog = create_catalog(archive / "archive.sqlite3")
    try:
        catalog.execute("DELETE FROM locations")
        catalog.commit()
    finally:
        catalog.close()
    missing = run_search("--archive", str(archive), "1")
    assert missing.returncode != 0
    assert "run mailarchiver refresh-locations" in missing.stderr
    assert "Traceback" not in missing.stderr
    refreshed = subprocess.run(
        [sys.executable, "-m", "mailarchiver", "--archive", str(archive), "refresh-locations"], capture_output=True, check=False
    )
    assert refreshed.returncode == 0, refreshed.stderr
    displayed = subprocess.run(
        [sys.executable, "-m", "mailarchiver.mailsearch", "--archive", str(archive), "1"], capture_output=True, check=False
    )
    assert displayed.stdout == render_message(raw, False, False).encode()


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


def test_mailsearch_decodes_legacy_catalog_subjects(tmp_path: Path) -> None:
    """Requirement: search output decodes historical RFC 2047 catalog subjects without rewriting the archive."""
    archive, _ = make_archive(tmp_path)
    catalog = create_catalog(archive / "archive.sqlite3")
    try:
        catalog.execute("UPDATE messages SET subject = ?", ("=?utf-8?B?UmU6IFJvYXN0ZWQgQ2F1bGlmbG93ZXI=?=",))
        catalog.commit()
    finally:
        catalog.close()
    assert "subject:Re: Roasted Cauliflower" in run_search("--archive", str(archive)).stdout


def test_refresh_subjects_rewrites_legacy_catalog_values(tmp_path: Path) -> None:
    """Requirement: refresh-subjects replaces historical encoded catalog text from canonical MBOX mail."""
    archive, _ = make_archive(tmp_path)
    catalog = create_catalog(archive / "archive.sqlite3")
    try:
        catalog.execute("UPDATE messages SET subject = ?", ("=?utf-8?B?UmU6IFJvYXN0ZWQgQ2F1bGlmbG93ZXI=?=",))
        catalog.commit()
    finally:
        catalog.close()
    refreshed = subprocess.run(
        [sys.executable, "-m", "mailarchiver", "--archive", str(archive), "refresh-subjects"], capture_output=True, text=True, check=False
    )
    assert refreshed.returncode == 0, refreshed.stderr
    catalog = create_catalog(archive / "archive.sqlite3")
    try:
        assert catalog.execute("SELECT subject FROM messages").fetchone() == ("planning meeting",)
    finally:
        catalog.close()


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
