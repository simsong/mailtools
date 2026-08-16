"""Requirements: Date uses earliest valid Received fallback before path year."""

from pathlib import Path

from mailarchiver.message import parse_message


def test_received_fallback_uses_earliest_valid_header() -> None:
    raw = b"\n".join(
        [
            b"Message-ID: <received@example>",
            b"From: sender@example.net",
            b"Received: by later.example; Fri, 2 Feb 2024 12:00:00 +0000",
            b"Received: by earlier.example; Thu, 1 Feb 2024 12:00:00 +0000",
            b"",
            b"body",
        ]
    )
    parsed = parse_message(raw, Path("/input/2020/message.eml"), None)
    assert parsed.date_source == "received"
    assert parsed.date_utc.startswith("2024-02-01")
