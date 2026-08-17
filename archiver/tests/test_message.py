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


def test_subject_is_decoded_and_unfolded() -> None:
    """Requirement: catalog subjects decode RFC 2047 words without modifying source bytes."""
    raw = b"\n".join(
        [
            b"Message-ID: <subject@example>",
            b"From: sender@example.net",
            b"Subject: =?utf-8?B?UmU6IE5ZVGltZXM6IFlvdSBXb27igJl0IFdhbnQgdG8gU2hhcmUgVGhpcyBS?=",
            b" =?utf-8?B?b2FzdGVkIENhdWxpZmxvd2Vy?=",
            b"Date: Thu, 1 Feb 2024 12:00:00 +0000",
            b"",
            b"body",
        ]
    )
    assert parse_message(raw, Path("/input/2024/message.eml"), None).subject == "Re: NYTimes: You Won’t Want to Share This Roasted Cauliflower"
