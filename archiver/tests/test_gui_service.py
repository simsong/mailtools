"""Requirements: the GUI reuses search semantics and preserves exported mail."""

from __future__ import annotations

import base64
import hashlib
import mailbox
import subprocess
import sys
import time
from pathlib import Path

import pytest

from mailarchiver.catalog import address_pk, create_catalog, create_search
from mailarchiver.gui_service import (
    RAW_PART_ID,
    attachment_content,
    describe_message,
    is_risky,
    message_previews,
    render_part,
    search_page,
    write_attachment,
    write_message,
)
from mailarchiver.gui_app import GuiApi
from mailarchiver.search import index_message


SIMPLE_MESSAGE = (
    b"Message-ID: <simple@example>\nFrom: sender@example.net\nTo: recipient@example.net\n"
    b"Subject: annual plan\nDate: Wed, 03 Jan 2024 10:00:00 +0000\n\nThe report is ready.\n"
)
MULTIPART_MESSAGE = (
    b"Message-ID: <multipart@example>\nFrom: sender@example.net\nTo: recipient@example.net\n"
    b"Subject: multipart message\nDate: Thu, 04 Jan 2024 10:00:00 +0000\n"
    b"Content-Type: multipart/mixed; boundary=outer\n\n"
    b"--outer\nContent-Type: multipart/alternative; boundary=alternative\n\n"
    b"--alternative\nContent-Type: text/plain; charset=utf-8\n\nPlain version.\n"
    b"--alternative\nContent-Type: text/html; charset=utf-8\n\n"
    b'<html><body onload="bad()"><script>bad()</script><p>HTML version.</p>'
    b'<img src="cid:logo"><img src="https://tracker.example/pixel"></body></html>\n'
    b"--alternative--\n"
    b"--outer\nContent-Type: image/png\nContent-ID: <logo>\nContent-Disposition: inline; filename=logo.png\n"
    b"Content-Transfer-Encoding: base64\n\naW1hZ2U=\n"
    b"--outer\nContent-Type: application/pdf\nContent-Disposition: attachment; filename=../report.pdf\n"
    b"Content-Transfer-Encoding: base64\n\nJVBERi0xLjQK\n"
    b"--outer--\n"
)


def make_gui_archive(tmp_path: Path) -> Path:
    archive = tmp_path / "archive"
    archive.mkdir()
    catalog = create_catalog(archive / "archive.sqlite3")
    search = create_search(archive / "search.sqlite3")
    try:
        sender = address_pk(catalog, "sender@example.net")
        recipient = address_pk(catalog, "recipient@example.net")
        for raw, message_id, subject, timestamp in (
            (SIMPLE_MESSAGE, "simple@example", "annual plan", "2024-01-03T10:00:00+00:00"),
            (MULTIPART_MESSAGE, "multipart@example", "multipart message", "2024-01-04T10:00:00+00:00"),
        ):
            cursor = catalog.execute(
                "INSERT INTO messages(message_id_normalized, sha256, sender_address_pk, subject, date_utc, date_source, category) "
                "VALUES (?, ?, ?, ?, ?, 'date', 'Archive')",
                (message_id, hashlib.sha256(raw).hexdigest(), sender, subject, timestamp),
            )
            catalog.execute("INSERT INTO recipients(message_pk, address_pk) VALUES (?, ?)", (cursor.lastrowid, recipient))
            index_message(search, raw, False)
        catalog.commit()
        search.commit()
    finally:
        catalog.close()
        search.close()
    box = mailbox.mbox(archive / "2024-Archive1.mbox")
    try:
        box.add(SIMPLE_MESSAGE)
        box.add(MULTIPART_MESSAGE)
        box.flush()
    finally:
        box.close()
    refreshed = subprocess.run(
        [sys.executable, "-m", "mailarchiver", "--archive", str(archive), "refresh-locations"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert refreshed.returncode == 0, refreshed.stderr
    return archive


def test_gui_search_field_preserves_selector_and_quote_semantics(tmp_path: Path) -> None:
    """Requirement: selectors and quoted phrases can coexist in one GUI search field."""
    archive = make_gui_archive(tmp_path)

    assert [result.subject for result in search_page(archive, "subject:annual report").results] == ["annual plan"]
    assert search_page(archive, 'subject:"annual report"').results == []
    assert [result.subject for result in search_page(archive, 'subject:"annual plan" report').results] == ["annual plan"]


def test_gui_search_sorting_is_whitelisted_and_stable(tmp_path: Path) -> None:
    """Requirement: GUI results sort by date, subject, or sender in either direction."""
    archive = make_gui_archive(tmp_path)

    ascending = search_page(archive, "", sort_by="subject", direction="ascending")
    descending = search_page(archive, "", sort_by="subject", direction="descending")

    assert [result.subject for result in ascending.results] == ["annual plan", "multipart message"]
    assert [result.subject for result in descending.results] == ["multipart message", "annual plan"]
    with pytest.raises(ValueError):
        search_page(archive, "", sort_by="subject; DROP TABLE messages")


def test_gui_search_results_include_indexed_attachment_counts(tmp_path: Path) -> None:
    """Requirement: result rows receive attachment counts without rereading canonical MBOX data."""
    archive = make_gui_archive(tmp_path)

    results = search_page(archive, "", sort_by="date", direction="ascending").results

    assert [(result.message_pk, result.attachment_count) for result in results] == [(1, 0), (2, 2)]


def test_gui_loads_indexed_previews_on_its_background_worker(tmp_path: Path) -> None:
    """Requirement: result metadata is independent from asynchronously loaded body previews."""
    archive = make_gui_archive(tmp_path)
    assert [(item.message_pk, item.preview) for item in message_previews(archive, [1, 2])] == [
        (1, "The report is ready."),
        (2, "Plain version."),
    ]
    api = GuiApi(archive)
    try:
        assert api.request_previews([1, 2])
        deadline = time.monotonic() + 2
        while (batch := api.take_previews([1, 2]))["pending"] and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        api.close()

    assert not batch["pending"]
    assert batch["error"] is None
    assert [(item["message_pk"], item["preview"]) for item in batch["previews"]] == [
        (1, "The report is ready."),
        (2, "Plain version."),
    ]


def test_gui_selects_multipart_views_and_sanitizes_html(tmp_path: Path) -> None:
    """Requirement: body alternatives are selectable and HTML is inert with remote content blocked."""
    archive = make_gui_archive(tmp_path)
    view = describe_message(archive, 2)
    plain_id = next(part.part_id for part in view.body_parts if part.content_type == "text/plain")
    html_id = next(part.part_id for part in view.body_parts if part.content_type == "text/html")

    assert {part.content_type for part in view.body_parts} == {"text/plain", "text/html", "message/rfc822"}
    assert view.preferred_part_id == html_id
    assert [(item.filename, item.preview) for item in view.attachments] == [("logo.png", "image"), ("report.pdf", "pdf")]
    assert render_part(archive, 2, plain_id).content == "Plain version."
    blocked = render_part(archive, 2, html_id)
    assert "<script" not in blocked.content
    assert "onload" not in blocked.content
    assert "data:image/png;base64,aW1hZ2U=" in blocked.content
    assert "tracker.example" not in blocked.content
    assert blocked.remote_content_blocked
    allowed = render_part(archive, 2, html_id, allow_remote=True)
    assert "https://tracker.example/pixel" in allowed.content
    assert not allowed.remote_content_blocked
    assert "Subject: multipart message" in render_part(archive, 2, RAW_PART_ID).content


def test_gui_exports_exact_eml_and_decoded_attachment(tmp_path: Path) -> None:
    """Requirement: .eml export preserves RFC 5322 bytes and attachment export decodes the selected part."""
    archive = make_gui_archive(tmp_path)
    view = describe_message(archive, 2)
    pdf = next(item for item in view.attachments if item.content_type == "application/pdf")
    eml_path, pdf_path = tmp_path / "message.eml", tmp_path / "report.pdf"

    write_message(archive, 2, eml_path)
    write_attachment(archive, 2, pdf.part_id, pdf_path)

    assert eml_path.read_bytes() == MULTIPART_MESSAGE
    assert hashlib.sha256(eml_path.read_bytes()).hexdigest() == hashlib.sha256(MULTIPART_MESSAGE).hexdigest()
    assert pdf_path.read_bytes() == b"%PDF-1.4\n"
    content = attachment_content(archive, 2, pdf.part_id)
    assert base64.b64decode(content.content_base64) == pdf_path.read_bytes()
    assert content.filename == "report.pdf"


def test_gui_flags_executable_attachment_types() -> None:
    """Requirement: opening executable-looking attachments requires explicit confirmation."""
    assert is_risky("installer.dmg", "application/octet-stream")
    assert is_risky("script", "application/x-sh")
    assert not is_risky("report.pdf", "application/pdf")
