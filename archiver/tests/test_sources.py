"""Requirements: source fingerprints verify complete files and prior-length prefixes."""

import hashlib
from pathlib import Path

from mailarchiver.sources import sha256_file_with_prefix


def test_one_pass_hashing_returns_prefix_and_complete_sha256(tmp_path: Path) -> None:
    path = tmp_path / "source.mbox"
    prior = b"complete old source bytes\n"
    appended = b"From sender@example Fri Feb  2 00:00:00 2024\nmessage\n"
    path.write_bytes(prior + appended)

    hashes = sha256_file_with_prefix(path, len(prior))

    assert hashes.prefix_sha256 == hashlib.sha256(prior).hexdigest()
    assert hashes.sha256 == hashlib.sha256(prior + appended).hexdigest()
