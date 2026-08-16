"""Requirements: FTS indexes preferred body text, excluding attachments by default."""

from mailarchiver.search import message_text


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
