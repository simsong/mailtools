"""Black-box acceptance tests for requirements in doc/end-to-end-tests.md."""

from __future__ import annotations

import hashlib
import mailbox
import os
import signal
import sqlite3
import subprocess
import sys
from pathlib import Path
from shutil import copy, copytree

import pytest


TEST_DATA = Path(__file__).parent / "data"


def emlx_message_bytes(path: Path) -> bytes:
    with path.open("rb") as source:
        size = int(source.readline())
        return source.read(size)


@pytest.fixture
def source_mail(tmp_path: Path) -> tuple[Path, dict[str, bytes]]:
    source = tmp_path / "source"
    source.mkdir()
    mbox = source / "three_messages.mbox"
    copy(TEST_DATA / "three_messages.mbox", mbox)
    copytree(TEST_DATA / "emlx_maildir", source / "emlx_maildir")
    messages = mailbox_message_bytes(mbox)
    return source, {
        "sent": messages[0],
        "collision_one": messages[2],
        "collision_two": emlx_message_bytes(source / "emlx_maildir/2024/001-collision.emlx"),
        "infected": emlx_message_bytes(source / "emlx_maildir/2024/infected/003-infected.emlx"),
    }


def run_ingest(source: Path, archive: Path, owner_names: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "mailarchiver",
            "--archive",
            str(archive),
            "ingest",
            "--owner-names-file",
            str(owner_names),
            "--clamav",
            str(source),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def mailbox_message_bytes(path: Path) -> list[bytes]:
    box = mailbox.mbox(path, factory=None, create=False)
    try:
        return [box.get_bytes(key, from_=False) for key in box.iterkeys()]
    finally:
        box.close()


def assert_success(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, result.stdout + result.stderr


def test_ingest_routes_preserves_and_indexes_messages(
    source_mail: tuple[Path, dict[str, bytes]], tmp_path: Path
) -> None:
    """Requirements: canonical preservation, dedupe, routing, FTS, and audit log."""
    source, raw = source_mail
    archive = tmp_path / "archive"
    owner_names = Path(__file__).parents[1] / "owner-names.txt"

    result = run_ingest(source, archive, owner_names)
    assert_success(result)
    assert "completed:" in result.stderr
    assert "processed=6" in result.stderr
    assert "files_processed=4" in result.stderr
    assert "started:" in result.stderr
    assert "starting ClamAV:" in result.stderr
    assert "ingesting:" in result.stderr
    assert "file=" in result.stderr
    assert "seen_skipped=" in result.stderr
    assert "  year    sent    received    people" in result.stdout
    assert "  2024       1           2" in result.stdout
    assert "top senders" in result.stdout

    assert mailbox_message_bytes(archive / "2024-Sent1.mbox") == [raw["sent"]]
    assert mailbox_message_bytes(archive / "2024-Archive1.mbox") == [
        raw["collision_one"],
        raw["collision_two"],
    ]
    assert len(mailbox_message_bytes(archive / "INFECTED1.mbox")) == 1
    assert all(b"autosave@example" not in item for item in mailbox_message_bytes(archive / "2024-Sent1.mbox"))

    catalog = sqlite3.connect(archive / "archive.sqlite3")
    try:
        assert catalog.execute("SELECT count(*) FROM messages").fetchone() == (4,)
        assert catalog.execute("SELECT count(*) FROM locations").fetchone() == (4,)
        assert catalog.execute("SELECT count(*) FROM observations").fetchone() == (6,)
        assert catalog.execute("SELECT count(*) FROM source_files").fetchone() == (4,)
        fingerprints = {
            Path(path): (modified_at_ns, byte_length, sha256)
            for path, modified_at_ns, byte_length, sha256 in catalog.execute(
                "SELECT source_path, modified_at_ns, byte_length, sha256 FROM source_files"
            )
        }
        for path in source.rglob("*"):
            if path.is_file():
                stat = path.stat()
                assert fingerprints[path.resolve()] == (
                    stat.st_mtime_ns,
                    stat.st_size,
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )
        assert catalog.execute(
            "SELECT date_source FROM messages WHERE message_id_normalized = 'infected@example'"
        ).fetchone() == ("path-year",)
        assert catalog.execute(
            "SELECT disposition FROM observations WHERE detail = 'X-Apple-Auto-Saved'"
        ).fetchone() == ("autosave-excluded",)
        assert catalog.execute(
            "SELECT count(*) FROM messages WHERE message_id_normalized = 'collision@example'"
        ).fetchone() == (2,)
        assert catalog.execute(
            "SELECT sha256 FROM messages WHERE message_id_normalized = 'infected@example'"
        ).fetchone() == (hashlib.sha256(raw["infected"]).hexdigest(),)
        assert catalog.execute("SELECT count(*) FROM email_addresses").fetchone() == (3,)
        assert catalog.execute("SELECT count(*) FROM messages JOIN email_addresses ON email_addresses.address_pk = messages.sender_address_pk WHERE address = 'sender@example.net'").fetchone() == (3,)
    finally:
        catalog.close()

    search = sqlite3.connect(archive / "search.sqlite3")
    try:
        infected_sha256 = hashlib.sha256(raw["infected"]).hexdigest()
        assert search.execute("SELECT count(*) FROM message_fts").fetchone() == (3,)
        assert search.execute("SELECT count(*) FROM message_fts WHERE sha256 = ?", (infected_sha256,)).fetchone() == (0,)
    finally:
        search.close()

    refreshed = subprocess.run(
        [sys.executable, "-m", "mailarchiver", "--archive", str(archive), "refresh-index"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert_success(refreshed)
    search = sqlite3.connect(archive / "search.sqlite3")
    try:
        assert search.execute("SELECT count(*) FROM message_fts").fetchone() == (3,)
        assert search.execute("SELECT count(*) FROM message_fts WHERE sha256 = ?", (infected_sha256,)).fetchone() == (0,)
    finally:
        search.close()
    assert (archive / "2024-Archive1.mbox.sha256").is_file()
    assert (archive / "INFECTED1.mbox.sha256").is_file()
    assert not (archive / ".mailarchiver-pending.json").exists()


def test_refresh_index_excludes_quarantine_mailboxes(tmp_path: Path) -> None:
    """Requirement: FTS rebuild excludes infected and malformed quarantine mail."""
    archive = tmp_path / "archive"
    archive.mkdir()
    messages = {
        "2024-Archive1.mbox": b"Message-ID: <normal@example>\nSubject: normal\n\nnormal body\n",
        "INFECTED.mbox": b"Message-ID: <infected@example>\nSubject: infected\n\ninfected body\n",
        "MALFORMED1.mbox": b"Message-ID: <malformed@example>\nSubject: malformed\n\nmalformed body\n",
    }
    for filename, raw in messages.items():
        box = mailbox.mbox(archive / filename, create=True)
        try:
            box.add(raw)
            box.flush()
        finally:
            box.close()

    refreshed = subprocess.run(
        [sys.executable, "-m", "mailarchiver", "--archive", str(archive), "refresh-index"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert_success(refreshed)
    search = sqlite3.connect(archive / "search.sqlite3")
    try:
        assert search.execute("SELECT sha256 FROM message_fts").fetchall() == [
            (hashlib.sha256(messages["2024-Archive1.mbox"]).hexdigest(),)
        ]
    finally:
        search.close()


def test_unchanged_source_files_are_skipped_wholesale(source_mail: tuple[Path, dict[str, bytes]], tmp_path: Path) -> None:
    """Requirements: matching source-file SHA-256 avoids per-message reingest."""
    source, _ = source_mail
    archive = tmp_path / "archive"
    owner_names = Path(__file__).parents[1] / "owner-names.txt"
    assert_success(run_ingest(source, archive, owner_names))
    before = {path.name: path.read_bytes() for path in archive.glob("*.mbox")}
    touched = source / "three_messages.mbox"
    stat = touched.stat()
    os.utime(touched, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))

    rerun = run_ingest(source, archive, owner_names)
    assert_success(rerun)

    assert {path.name: path.read_bytes() for path in archive.glob("*.mbox")} == before
    catalog = sqlite3.connect(archive / "archive.sqlite3")
    try:
        assert catalog.execute("SELECT count(*) FROM messages").fetchone() == (4,)
        assert catalog.execute("SELECT count(*) FROM ingest_runs").fetchone() == (2,)
        assert catalog.execute("SELECT count(*) FROM observations").fetchone() == (6,)
        assert catalog.execute("SELECT count(*) FROM source_files WHERE completed_run = 2").fetchone() == (4,)
        assert catalog.execute(
            "SELECT modified_at_ns FROM source_files WHERE source_path = ?", (str(touched.resolve()),)
        ).fetchone() == (touched.stat().st_mtime_ns,)
    finally:
        catalog.close()
    assert "processed=0" in rerun.stderr
    assert "files_processed=4" in rerun.stderr


def test_completed_file_is_published_before_later_source_failure(tmp_path: Path) -> None:
    """Requirement: source discovery never delays publication of an earlier complete file."""
    source = tmp_path / "first.eml"
    raw = (
        b"Message-ID: <first-before-failure@example>\n"
        b"From: sender@example.net\n"
        b"Date: Thu, 1 Feb 2024 12:00:00 +0000\n\nfirst body\n"
    )
    source.write_bytes(raw)
    archive = tmp_path / "archive"
    owner_names = Path(__file__).parents[1] / "owner-names.txt"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mailarchiver",
            "--archive",
            str(archive),
            "ingest",
            "--owner-names-file",
            str(owner_names),
            "--clamav",
            str(source),
            str(tmp_path / "missing-source"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "source not found" in result.stderr
    assert mailbox_message_bytes(archive / "2024-Archive1.mbox") == [raw]
    catalog = sqlite3.connect(archive / "archive.sqlite3")
    try:
        assert catalog.execute("SELECT count(*) FROM messages").fetchone() == (1,)
        assert catalog.execute("SELECT count(*) FROM source_files").fetchone() == (1,)
    finally:
        catalog.close()


def test_mbox_append_resumes_after_verified_prefix(tmp_path: Path) -> None:
    """Requirement: appended MBOX input resumes at the old verified byte boundary."""
    source = tmp_path / "source.mbox"
    first = b"Message-ID: <first@example>\nFrom: sender@example.net\nDate: Thu, 1 Feb 2024 12:00:00 +0000\n\nfirst\n"
    second = b"Message-ID: <second@example>\nFrom: sender@example.net\nDate: Fri, 2 Feb 2024 12:00:00 +0000\n\nsecond\n"
    box = mailbox.mbox(source, create=True)
    try:
        box.add(first)
        box.flush()
    finally:
        box.close()
    archive = tmp_path / "archive"
    owner_names = Path(__file__).parents[1] / "owner-names.txt"
    assert_success(run_ingest(source, archive, owner_names))
    first_length = source.stat().st_size
    box = mailbox.mbox(source, create=False)
    try:
        box.add(second)
        box.flush()
    finally:
        box.close()

    result = run_ingest(source, archive, owner_names)

    assert_success(result)
    assert "processed=1" in result.stderr
    catalog = sqlite3.connect(archive / "archive.sqlite3")
    try:
        assert catalog.execute("SELECT count(*) FROM messages").fetchone() == (2,)
        assert catalog.execute("SELECT count(*) FROM observations").fetchone() == (2,)
        length, sha256 = catalog.execute("SELECT byte_length, sha256 FROM source_files").fetchone()
        assert length == source.stat().st_size > first_length
        assert sha256 == hashlib.sha256(source.read_bytes()).hexdigest()
    finally:
        catalog.close()


def test_malformed_subject_is_archived_with_metadata_defect(tmp_path: Path) -> None:
    """Requirement: malformed display metadata does not block canonical preservation."""
    source = tmp_path / "2003" / "spam.eml"
    source.parent.mkdir()
    subject = "=?EUC-KR?B? KLGks00pvY?= trailing text"
    raw = b"\n".join(
        [
            b"Message-ID: <spam@example>",
            b"From: sender@example.net",
            f"Subject: {subject}".encode(),
            b"Date: Mon, 30 Jun 2003 19:50:44 -0400",
            b"",
            b"body\n",
        ]
    )
    source.write_bytes(raw)
    archive = tmp_path / "archive"
    owner_names = Path(__file__).parents[1] / "owner-names.txt"

    result = run_ingest(source, archive, owner_names)

    assert_success(result)
    assert mailbox_message_bytes(archive / "2003-Archive1.mbox") == [raw]
    catalog = sqlite3.connect(archive / "archive.sqlite3")
    try:
        assert catalog.execute("SELECT subject FROM messages").fetchone() == (subject,)
        assert catalog.execute("SELECT field, detail FROM metadata_defects").fetchone() == (
            "Subject",
            "HeaderParseError: Base64 decoding error",
        )
    finally:
        catalog.close()


def test_report_counts_years_people_and_correspondents(source_mail: tuple[Path, dict[str, bytes]], tmp_path: Path) -> None:
    """Requirement: owner addresses are catalogued but omitted from top correspondents."""
    source, _ = source_mail
    archive = tmp_path / "archive"
    owner_names = Path(__file__).parents[1] / "owner-names.txt"
    assert_success(run_ingest(source, archive, owner_names))
    catalog = sqlite3.connect(archive / "archive.sqlite3")
    try:
        catalog.execute(
            "INSERT OR IGNORE INTO recipients(message_pk, address_pk) "
            "SELECT message_pk, sender_address_pk FROM messages WHERE category = 'Sent'"
        )
        catalog.commit()
    finally:
        catalog.close()

    result = subprocess.run(
        [sys.executable, "-m", "mailarchiver", "--archive", str(archive), "report", "--year", "2024", "--top", "2"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    assert "  2024       1           2         3" in lines
    assert "sender@example.net           2  2024-01-03  2024-01-04" in lines
    assert "recipient@example.net           3  2024-01-02  2024-01-04" in lines
    assert "simsong@example.com" not in result.stdout


def test_report_labels_missing_sender(tmp_path: Path) -> None:
    """Requirement: unresolved sender metadata is explicit rather than a blank table row."""
    source = tmp_path / "2024" / "message.eml"
    source.parent.mkdir()
    source.write_bytes(b"Message-ID: <missing@example>\nDate: Thu, 1 Feb 2024 12:00:00 +0000\n\nbody\n")
    archive = tmp_path / "archive"
    owner_names = Path(__file__).parents[1] / "owner-names.txt"
    assert_success(run_ingest(source, archive, owner_names))

    result = subprocess.run(
        [sys.executable, "-m", "mailarchiver", "--archive", str(archive), "report"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "(missing sender)" in result.stdout


def test_interrupt_stops_cleanly(source_mail: tuple[Path, dict[str, bytes]], tmp_path: Path) -> None:
    """Requirement: Ctrl-C exits cleanly without an exception traceback."""
    source, _ = source_mail
    archive = tmp_path / "archive"
    owner_names = Path(__file__).parents[1] / "owner-names.txt"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "mailarchiver",
            "--archive",
            str(archive),
            "ingest",
            "--owner-names-file",
            str(owner_names),
            "--clamav",
            str(source),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stderr.readline().startswith("started:")
    process.send_signal(signal.SIGINT)
    stdout, stderr = process.communicate(timeout=20)
    assert process.returncode == 130, stdout + stderr
    assert "interrupted:" in stderr
    assert "Traceback" not in stderr
    assert stdout.startswith("year    sent    received    people\n")


def test_parser_failure_records_source_identity_and_failed_run(tmp_path: Path) -> None:
    """Requirement: an unexpected parser failure is identifiable and safely rerunnable."""
    source = tmp_path / "undated.eml"
    raw = b"Message-ID: <undated@example>\nFrom: sender@example.net\n\nbody\n"
    source.write_bytes(raw)
    archive = tmp_path / "archive"
    owner_names = Path(__file__).parents[1] / "owner-names.txt"

    result = run_ingest(source, archive, owner_names)

    assert result.returncode != 0
    digest = hashlib.sha256(raw).hexdigest()
    assert f"source offset 0; sha256={digest}" in result.stderr
    catalog = sqlite3.connect(archive / "archive.sqlite3")
    try:
        completed_at, run_result, detail = catalog.execute(
            "SELECT completed_at, result, detail FROM ingest_runs"
        ).fetchone()
        assert completed_at is not None
        assert run_result == "failed"
        assert detail.startswith("RuntimeError: failed to parse")
        assert catalog.execute(
            "SELECT source_path, source_offset, source_sha256, disposition, detail FROM observations"
        ).fetchone() == (str(source), 0, digest, "error", f"ValueError: no date or year path fallback for {source}")
    finally:
        catalog.close()
    assert not list(archive.glob("*.mbox"))


def test_fresh_catalog_is_refused_beside_existing_mbox(tmp_path: Path) -> None:
    """Requirement: deleting only the catalog cannot cause duplicate canonical output."""
    source = tmp_path / "source.eml"
    source.write_bytes(b"Message-ID: <one@example>\nDate: Thu, 1 Feb 2024 12:00:00 +0000\n\nbody\n")
    archive = tmp_path / "archive"
    archive.mkdir()
    existing = archive / "2024-Archive1.mbox"
    existing.write_bytes(b"existing canonical bytes\n")
    owner_names = Path(__file__).parents[1] / "owner-names.txt"

    result = run_ingest(source, archive, owner_names)

    assert result.returncode != 0
    assert "use a new empty archive directory" in result.stderr
    assert existing.read_bytes() == b"existing canonical bytes\n"
    assert not (archive / "archive.sqlite3").exists()


@pytest.mark.parametrize(
    ("source_name", "contents", "diagnostic"),
    [
        ("missing", None, "source not found:"),
        ("7.partial.emlx", b"5\nbody\n", "unsupported source: Apple Mail partial message"),
    ],
)
def test_unusable_source_fails_cleanly(
    tmp_path: Path, source_name: str, contents: bytes | None, diagnostic: str
) -> None:
    """Requirement: missing or incomplete Apple Mail input cannot look successful."""
    source = tmp_path / source_name
    if contents is not None:
        source.write_bytes(contents)
    archive = tmp_path / "archive"
    owner_names = Path(__file__).parents[1] / "owner-names.txt"

    result = run_ingest(source, archive, owner_names)

    assert result.returncode == 1
    assert diagnostic in result.stderr
    assert "Traceback" not in result.stderr
    assert not list(archive.glob("*.mbox"))
