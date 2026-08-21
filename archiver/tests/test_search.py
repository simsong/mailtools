"""Requirements: FTS indexes preferred body text, excluding attachments by default."""

import sqlite3
import warnings

from bs4 import XMLParsedAsHTMLWarning

from mailarchiver.search import index_message_safely, message_text


def test_plain_body_wins_and_attachment_requires_opt_in() -> None:
    raw = b"\n".join(
        [
            b"From: sender@example.net",
            b"Subject: preferred body",
            b"Content-Type: multipart/mixed; boundary=x",
            b"",
            b"--x",
            b"Content-Type: text/plain; charset=utf-8",
            b"",
            b"plain body",
            b"--x",
            b"Content-Type: text/html; charset=utf-8",
            b"",
            b"<p>html body</p>",
            b"--x",
            b"Content-Type: text/plain; name=attached.txt",
            b"Content-Disposition: attachment; filename=attached.txt",
            b"",
            b"attachment words",
            b"--x--",
        ]
    )
    default = message_text(raw, index_attachments=False)
    assert "plain body" in default
    assert "html body" not in default
    assert "attachment words" not in default
    assert "attachment words" in message_text(raw, index_attachments=True)


def test_xml_looking_html_is_rendered_without_parser_warning() -> None:
    """Requirement: text/html remains best-effort derived content even when it resembles XML."""
    raw = b"\n".join(
        [
            b"Content-Type: text/html; charset=utf-8",
            b"",
            b'<?xml version="1.0"?><html><body><p>message body</p></body></html>',
        ]
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        rendered = message_text(raw, index_attachments=False)

    assert "message body" in rendered
    assert not any(item.category is XMLParsedAsHTMLWarning for item in caught)


def test_index_failure_is_recorded_without_raising() -> None:
    """Requirement: disposable search extraction cannot veto canonical publication."""
    catalog = sqlite3.connect(":memory:")
    search = sqlite3.connect(":memory:")
    catalog.execute(
        "CREATE TABLE metadata_defects (message_pk INTEGER, field TEXT, detail TEXT, UNIQUE(message_pk, field, detail))"
    )

    index_message_safely(catalog, search, 7, b"Subject: retained\n\nbody", False)

    field, detail = catalog.execute("SELECT field, detail FROM metadata_defects").fetchone()
    assert field == "search-index"
    assert "no such table: message_fts" in detail
