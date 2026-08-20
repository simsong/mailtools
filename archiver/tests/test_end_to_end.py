"""Black-box acceptance tests for requirements in doc/end-to-end-tests.md."""

from __future__ import annotations

import hashlib
import mailbox
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
    assert "started:" in result.stderr
    assert "file=" in result.stderr
    assert "seen_skipped=" in result.stderr
    assert "year\tsent\treceived\tpeople" in result.stdout
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
        assert search.execute("SELECT count(*) FROM message_fts WHERE message_fts MATCH 'Eicar'").fetchone() == (0,)
    finally:
        search.close()
    assert (archive / "2024-Archive1.mbox.sha256").is_file()
    assert (archive / "INFECTED1.mbox.sha256").is_file()
    assert not (archive / ".mailarchiver-pending.json").exists()


def test_rerun_is_idempotent_and_reviewable(source_mail: tuple[Path, dict[str, bytes]], tmp_path: Path) -> None:
    """Requirements: an unchanged source does not alter canonical mail or logical messages."""
    source, _ = source_mail
    archive = tmp_path / "archive"
    owner_names = Path(__file__).parents[1] / "owner-names.txt"
    assert_success(run_ingest(source, archive, owner_names))
    before = {path.name: path.read_bytes() for path in archive.glob("*.mbox")}

    assert_success(run_ingest(source, archive, owner_names))

    assert {path.name: path.read_bytes() for path in archive.glob("*.mbox")} == before
    catalog = sqlite3.connect(archive / "archive.sqlite3")
    try:
        assert catalog.execute("SELECT count(*) FROM messages").fetchone() == (4,)
        assert catalog.execute("SELECT count(*) FROM ingest_runs").fetchone() == (2,)
        assert catalog.execute("SELECT count(*) FROM observations").fetchone() == (12,)
    finally:
        catalog.close()

    result = subprocess.run(
        [sys.executable, "-m", "mailarchiver", "--archive", str(archive), "review", "--run", "2"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "duplicate" in result.stdout


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
    assert "year\tsent\treceived\tpeople\n2024\t1\t3\t3" in result.stdout
    assert "top senders\nsender@example.net\t3" in result.stdout
    assert "top recipients\nrecipient@example.net\t4" in result.stdout
    assert "simsong@example.com" not in result.stdout


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
    assert stdout.startswith("year\tsent\treceived\tpeople\n")


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
