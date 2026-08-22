"""Requirements: archives use the versioned hybrid integrity format."""

from __future__ import annotations

import hashlib
import json
import mailbox
import subprocess
import sys
from pathlib import Path

from mailarchiver.standalone_verify import (
    INSTALLED_NAME,
    IntegrityMessage,
    install_archive_verifier,
    semantic_bytes,
    write_integrity_file,
)


def run_verifier(script: Path, archive: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", str(script), str(archive)],
        capture_output=True,
        text=True,
        check=False,
    )


def make_integrity_archive(tmp_path: Path) -> tuple[Path, Path, bytes]:
    raw = (
        b"Message-ID: <verify@example>\nFrom: sender@example\nTo: recipient@example\n"
        b"Delivered-To: mailbox@example\nSubject: integrity\nDate: Thu, 1 Feb 2024 12:00:00 +0000\n"
        b"Status: RO\n\nPreserve these bytes.\n"
    )
    path = tmp_path / "2024-Archive1.mbox"
    box = mailbox.mbox(path)
    try:
        box.add(raw)
        box.flush()
    finally:
        box.close()
    message = IntegrityMessage("verify@example", hashlib.sha256(raw).hexdigest(), raw)
    write_integrity_file(path, (message,), 1)
    return path, path.with_name(f"{path.name}.integrity"), raw


def test_standalone_verifier_checks_current_file_and_message_hashes(tmp_path: Path) -> None:
    """Requirement: the stdlib tool checks h1 MBOX, h2 raw, and h3 semantic hashes."""
    path, integrity, raw = make_integrity_archive(tmp_path)
    script = install_archive_verifier(tmp_path)

    valid = run_verifier(script, tmp_path)
    assert valid.returncode == 0, valid.stderr
    assert "Archive integrity verified." in valid.stdout
    lines = integrity.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["code"] for line in lines[1:4]] == ["h1", "h2", "h3"]
    fields = lines[-1].split("\t")
    assert [field[:3] for field in fields[2:]] == ["h2:", "h3:"]
    fields[-1] = "h3:" + "0" * 64
    lines[-1] = "\t".join(fields)
    integrity.write_text("\n".join(lines) + "\n", encoding="utf-8")
    bad_message = run_verifier(script, tmp_path)
    assert bad_message.returncode == 1
    assert "message 1 h3 mismatch" in bad_message.stderr

    write_integrity_file(
        path,
        (IntegrityMessage("verify@example", hashlib.sha256(raw).hexdigest(), raw),),
        1,
    )
    with path.open("ab") as output:
        output.write(b"damage")
    bad_file = run_verifier(script, tmp_path)
    assert bad_file.returncode == 1
    assert "h1 mismatch" in bad_file.stderr
    assert script.name == INSTALLED_NAME


def test_semantic_v1_selects_stable_delivery_headers_and_complete_body() -> None:
    """Requirement: h3 ignores mutable status but includes delivery identity and body bytes."""
    base = (
        b"From: sender@example\r\nTo: recipient@example\r\nDelivered-To: first@example\r\n"
        b"Subject: folded\r\n\tvalue\r\nDate: Thu, 1 Feb 2024 12:00:00 +0000\r\n"
        b"Message-ID: <same@example>\r\nStatus: RO\r\nReceived: trace one\r\n\r\nbody\r\n\r\n"
    )
    refolded = base.replace(b"Subject: folded\r\n\tvalue", b"Subject:  folded   value")
    mutable = refolded.replace(b"Status: RO", b"Status: O").replace(b"Received: trace one", b"Received: trace two")
    delivered = mutable.replace(b"Delivered-To: first@example", b"Delivered-To: second@example")
    changed_body = mutable.replace(b"body", b"changed body")

    assert semantic_bytes(base) == semantic_bytes(refolded) == semantic_bytes(mutable)
    assert semantic_bytes(mutable) != semantic_bytes(delivered)
    assert semantic_bytes(mutable) != semantic_bytes(changed_body)


def test_integrity_serialization_is_deterministic(tmp_path: Path) -> None:
    """Requirement: regenerating unchanged declarations and inputs reproduces exact bytes."""
    path, integrity, raw = make_integrity_archive(tmp_path)
    first = integrity.read_bytes()
    write_integrity_file(path, (IntegrityMessage("verify@example", hashlib.sha256(raw).hexdigest(), raw),), 1)
    assert integrity.read_bytes() == first


def test_verifier_accepts_multiple_digest_algorithms_for_one_standard(tmp_path: Path) -> None:
    """Requirement: one file may tag SHA-256 and SHA-512 digests of the same semantic input."""
    _, integrity, raw = make_integrity_archive(tmp_path)
    lines = integrity.read_text(encoding="utf-8").splitlines()
    h4 = {
        "code": "h4",
        "digest_algorithm": "sha512",
        "hash_standard": "semantic",
        "hash_version": 1,
        "id": "tag:simson.net,2026:mailarchiver/hash/semantic/v1/sha512",
        "same_input_as": "h3",
        "scope": "message",
        "type": "hash-standard",
    }
    lines.insert(4, json.dumps(h4, separators=(",", ":"), sort_keys=True))
    lines[-1] += f"\th4:{hashlib.sha512(semantic_bytes(raw)).hexdigest()}"
    integrity.write_text("\n".join(lines) + "\n", encoding="utf-8")
    script = install_archive_verifier(tmp_path)

    verified = run_verifier(script, tmp_path)

    assert verified.returncode == 0, verified.stderr


def test_message_id_field_is_json_null_when_header_is_absent(tmp_path: Path) -> None:
    """Requirement: the TSV diagnostic field does not invent a Message-ID."""
    raw = b"From: sender@example\nSubject: no identifier\n\nbody\n"
    path = tmp_path / "2024-Archive1.mbox"
    box = mailbox.mbox(path)
    try:
        box.add(raw)
        box.flush()
    finally:
        box.close()
    write_integrity_file(path, (IntegrityMessage(None, hashlib.sha256(raw).hexdigest(), raw),), 1)

    fields = path.with_name(f"{path.name}.integrity").read_text(encoding="utf-8").splitlines()[-1].split("\t")

    assert fields[1] == "null"
