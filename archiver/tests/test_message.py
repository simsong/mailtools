"""Requirements: dates fall back safely and malformed header bytes do not alter mail."""

import hashlib
from email import policy
from email.header import Header
from email.parser import BytesParser
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


def test_raw_8bit_received_header_resolves_date_without_altering_identity() -> None:
    """Requirement: malformed header encoding falls back without affecting preservation."""
    raw = b"\n".join(
        [
            b"Message-ID: <raw-received@example>",
            b"From: sender@example.net",
            b"Received: from caf\xe9.example; Thu, 1 Feb 2024 12:00:00 +0000",
            b"",
            b"body",
        ]
    )
    assert isinstance(BytesParser(policy=policy.compat32).parsebytes(raw)["Received"], Header)

    parsed = parse_message(raw, Path("/input/2020/message.eml"), None)

    assert parsed.date_source == "received"
    assert parsed.date_utc.startswith("2024-02-01")
    assert parsed.sha256 == hashlib.sha256(raw).hexdigest()


def test_raw_8bit_recipient_header_preserves_address() -> None:
    """Requirement: recipient metadata survives malformed display-name encoding."""
    raw = b"\n".join(
        [
            b"Message-ID: <raw-recipient@example>",
            b"From: sender@example.net",
            b"To: Jos\xe9 <recipient@example.net>",
            b"Date: Thu, 1 Feb 2024 12:00:00 +0000",
            b"",
            b"body",
        ]
    )
    assert isinstance(BytesParser(policy=policy.compat32).parsebytes(raw)["To"], Header)

    parsed = parse_message(raw, Path("/input/2020/message.eml"), None)

    assert parsed.recipients == ["recipient@example.net"]
    assert parsed.sha256 == hashlib.sha256(raw).hexdigest()


def test_malformed_base64_subject_falls_back_and_records_defect() -> None:
    """Requirement: broken RFC 2047 metadata never prevents raw-message preservation."""
    subject = "=?EUC-KR?B? KLGks00pvY?= trailing text"
    raw = b"\n".join(
        [
            b"Message-ID: <spam@example>",
            b"From: sender@example.net",
            f"Subject: {subject}".encode(),
            b"Date: Mon, 30 Jun 2003 19:50:44 -0400",
            b"",
            b"body",
        ]
    )

    parsed = parse_message(raw, Path("/input/2003/message.eml"), None)

    assert parsed.subject == subject
    assert [(defect.field, defect.detail) for defect in parsed.defects] == [
        ("Subject", "HeaderParseError: Base64 decoding error")
    ]
    assert parsed.sha256 == hashlib.sha256(raw).hexdigest()


def test_implausible_date_uses_received_fallback() -> None:
    """Requirement: an implausible year is not accepted for archive routing."""
    raw = b"\n".join(
        [
            b"Message-ID: <bad-year@example>",
            b"From: sender@example.net",
            b"Date: Tue, 14 Sep 0104 12:00:00 +0000",
            b"Received: by example.net; Mon, 30 Jun 2003 19:50:44 -0400",
            b"",
            b"body",
        ]
    )

    parsed = parse_message(raw, Path("/input/2003/message.eml"), None)

    assert parsed.date_source == "received"
    assert parsed.date_utc.startswith("2003-06-30")
    assert [(defect.field, defect.detail) for defect in parsed.defects] == [
        ("Date", "invalid or implausible date")
    ]


def test_sender_header_falls_back_when_from_is_missing() -> None:
    """Requirement: a real Sender header supplies a missing From identity."""
    raw = b"Sender: fallback@example.net\nDate: Thu, 1 Feb 2024 12:00:00 +0000\n\nbody\n"

    parsed = parse_message(raw, Path("/input/2024/message.eml"), None)

    assert parsed.sender == "fallback@example.net"
    assert ("From", "missing or invalid; used Sender header") in [
        (defect.field, defect.detail) for defect in parsed.defects
    ]


def test_google_chat_event_uses_embedded_actor_name() -> None:
    """Requirement: recognized Google Chat events expose a named non-email actor."""
    raw = b"\n".join(
        [
            b"X-GM-THRID: 1234",
            b"",
            b"sender {",
            b'  full_name: "Simson Garfinkel"',
            b"}",
            b'conversation_id: "conversation"',
            b"timestamp: 1369948644835641",
            b'event_id: "event"',
        ]
    )

    parsed = parse_message(raw, Path("/input/2013/message.eml"), None)

    assert parsed.sender == "Simson Garfinkel (Google Chat)"
    assert ("From", "missing; used Google Chat body identity") in [
        (defect.field, defect.detail) for defect in parsed.defects
    ]


def test_arbitrary_body_sender_text_is_not_treated_as_identity() -> None:
    """Requirement: ordinary body text cannot masquerade as Google Chat metadata."""
    raw = b'Date: Thu, 1 Feb 2024 12:00:00 +0000\n\nsender { full_name: "Impostor" }\n'

    parsed = parse_message(raw, Path("/input/2024/message.eml"), None)

    assert parsed.sender == ""


def test_quoted_nested_mbox_from_header_is_recovered() -> None:
    """Requirement: quoted nested-MBOX status prefixes do not hide a valid From header."""
    raw = b"\n".join(
        [
            b"Status: R",
            b"X-Status:",
            b">From nested@example.net  Sat Nov 23 07:40:54 2002",
            b"Return-Path: <nested@example.net>",
            b"From: Nested Sender <nested@example.net>",
            b"Date: Sat, 23 Nov 2002 07:40:54 +0000",
            b"",
            b"body",
        ]
    )

    parsed = parse_message(raw, Path("/input/2002/message.eml"), None)

    assert parsed.sender == "nested@example.net"
    assert ("From", "used quoted embedded MBOX From header") in [
        (defect.field, defect.detail) for defect in parsed.defects
    ]
