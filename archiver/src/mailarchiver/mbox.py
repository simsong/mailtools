"""Canonical MBOX writes, retrieval, recovery, and integrity generation."""

from __future__ import annotations

import errno
import hashlib
import mailbox
import os
import shutil
import sqlite3
from datetime import datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel

from .message import ParsedMessage
from .standalone_verify import IntegrityMessage, write_integrity_file


class DiskFullError(RuntimeError):
    """The archive cannot safely accept another message."""


class MboxLocation(BaseModel):
    byte_offset: int
    byte_length: int


class PendingPublication(BaseModel):
    filename: str
    prior_size: int
    file_existed: bool
    message_id: str
    sha256: str


PUBLICATION_JOURNAL = ".mailarchiver-pending.json"
MAX_AMBIGUOUS_FROM_LINES = 12


class PublicationRecovery(str, Enum):
    NONE = "none"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled-back"


def journal_publication(archive: Path, publication: PendingPublication) -> None:
    target = archive / PUBLICATION_JOURNAL
    temporary = target.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        output.write(publication.model_dump_json())
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(target)
    _sync_directory(archive)


def clear_publication_journal(archive: Path) -> None:
    (archive / PUBLICATION_JOURNAL).unlink(missing_ok=True)
    _sync_directory(archive)


def recover_publication(archive: Path, catalog: sqlite3.Connection, search: sqlite3.Connection) -> PublicationRecovery:
    """Finish or roll back the one durable in-flight message publication."""
    journal = archive / PUBLICATION_JOURNAL
    if not journal.exists():
        return PublicationRecovery.NONE
    publication = PendingPublication.model_validate_json(journal.read_text(encoding="utf-8"))
    committed = catalog.execute(
        "SELECT mbox_generations.filename, locations.byte_offset, locations.byte_length "
        "FROM messages JOIN locations USING (message_pk) JOIN mbox_generations USING (generation_pk) "
        "WHERE message_id_normalized = ? AND messages.sha256 = ?",
        (publication.message_id, publication.sha256),
    ).fetchone()
    if committed is not None:
        filename, offset, length = committed
        try:
            read_verified_location(
                archive / filename,
                MboxLocation(byte_offset=offset, byte_length=length),
                publication.sha256,
            )
        except ValueError as error:
            raise RuntimeError(f"committed pending publication failed validation for {filename}") from error
        clear_publication_journal(archive)
        return PublicationRecovery.COMMITTED
    path = archive / publication.filename
    if not path.exists() and not publication.file_existed:
        search.execute("DELETE FROM message_fts WHERE sha256 = ?", (publication.sha256,))
        search.execute("DELETE FROM attachment_fts WHERE sha256 = ?", (publication.sha256,))
        search.execute("DELETE FROM message_metadata WHERE sha256 = ?", (publication.sha256,))
        search.commit()
        clear_publication_journal(archive)
        return PublicationRecovery.ROLLED_BACK
    if not path.exists() or path.stat().st_size < publication.prior_size:
        raise RuntimeError(f"cannot recover pending publication for {path}")
    if publication.file_existed:
        with path.open("r+b") as output:
            output.truncate(publication.prior_size)
            output.flush()
            os.fsync(output.fileno())
    else:
        path.unlink()
    search.execute("DELETE FROM message_fts WHERE sha256 = ?", (publication.sha256,))
    search.execute("DELETE FROM attachment_fts WHERE sha256 = ?", (publication.sha256,))
    search.execute("DELETE FROM message_metadata WHERE sha256 = ?", (publication.sha256,))
    search.commit()
    clear_publication_journal(archive)
    return PublicationRecovery.ROLLED_BACK


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def mailbox_name(parsed: ParsedMessage, category: str) -> str:
    if category == "INFECTED":
        return "INFECTED1.mbox"
    return f"{datetime.fromisoformat(parsed.date_utc).year}-{category}1.mbox"


def add_message(box: mailbox.mbox, path: Path, raw: bytes) -> MboxLocation:
    prior_size = path.stat().st_size if path.exists() else 0
    if shutil.disk_usage(path.parent).free < len(raw) + 1024 * 1024:
        raise DiskFullError(f"insufficient free space before writing {path}")
    try:
        key = box.add(raw)
        box.flush()
        with path.open("rb") as persisted:
            os.fsync(persisted.fileno())
        start, stop = box._lookup(key)
        return MboxLocation(byte_offset=start, byte_length=stop - start)
    except OSError as error:
        if error.errno != errno.ENOSPC:
            raise
        box.close()
        with path.open("r+b") as destination:
            destination.truncate(prior_size)
        raise DiskFullError(f"disk full while writing {path}") from error


def _read_stored_payload(path: Path, location: MboxLocation) -> bytes:
    with path.open("rb") as source:
        source.seek(location.byte_offset)
        record = source.read(location.byte_length)
    envelope, separator, raw = record.partition(b"\n")
    if not separator or not envelope.startswith(b"From "):
        raise ValueError(f"invalid MBOX location in {path}")
    return raw


def read_location_candidates(path: Path, location: MboxLocation):
    """Yield possible originals for the standard library's ambiguous From quoting."""
    stored = _read_stored_payload(path, location)
    lines = stored.splitlines(keepends=True)
    ambiguous = [index for index, line in enumerate(lines) if line.startswith(b">From ")]
    masks = [(1 << len(ambiguous)) - 1, 0]
    if len(ambiguous) <= MAX_AMBIGUOUS_FROM_LINES:
        masks.extend(range(1 << len(ambiguous)))
    seen: set[bytes] = set()
    for mask in masks:
        candidate = list(lines)
        for bit, index in enumerate(ambiguous):
            if mask & (1 << bit):
                candidate[index] = candidate[index][1:]
        raw = b"".join(candidate)
        if raw not in seen:
            seen.add(raw)
            yield raw
    if stored == b"\n":
        yield b""


def read_location(path: Path, location: MboxLocation) -> bytes:
    """Read the conventional all-quoted-From interpretation of one MBOX record."""
    return next(read_location_candidates(path, location))


def read_verified_location(path: Path, location: MboxLocation, expected_sha256: str) -> bytes:
    """Select the original MBOX interpretation by its catalogued identity."""
    for raw in read_location_candidates(path, location):
        if hashlib.sha256(raw).hexdigest() == expected_sha256:
            return raw
    raise ValueError(f"MBOX location hash mismatch in {path}")


def write_integrity_files(archive: Path, catalog: sqlite3.Connection) -> None:
    """Regenerate every MBOX integrity sidecar from catalog-verified bytes."""
    for path in sorted(archive.glob("*.mbox")):
        rows = catalog.execute(
            "SELECT m.message_id_normalized, m.sha256, l.byte_offset, l.byte_length "
            "FROM messages m JOIN locations l USING (message_pk) "
            "JOIN mbox_generations g USING (generation_pk) WHERE g.filename = ? "
            "ORDER BY l.byte_offset",
            (path.name,),
        )
        count_row = catalog.execute(
            "SELECT COUNT(*) FROM locations JOIN mbox_generations USING (generation_pk) WHERE filename = ?",
            (path.name,),
        ).fetchone()
        assert count_row is not None
        message_count = int(count_row[0])

        def messages():
            for message_id, raw_sha256, offset, length in rows:
                raw = read_verified_location(
                    path,
                    MboxLocation(byte_offset=offset, byte_length=length),
                    raw_sha256,
                )
                header = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n").partition(b"\n\n")[0]
                has_message_id = any(
                    line.partition(b":")[0].lower() == b"message-id" for line in header.split(b"\n")
                )
                yield IntegrityMessage(
                    message_id=message_id if has_message_id else None,
                    raw_sha256=raw_sha256,
                    raw=raw,
                )

        digest = write_integrity_file(path, messages(), message_count)
        result = catalog.execute(
            "UPDATE mbox_generations SET sha256 = ?, message_count = ?, byte_count = ? WHERE filename = ?",
            (digest, message_count, path.stat().st_size, path.name),
        )
        if result.rowcount != 1:
            raise ValueError(f"MBOX has no catalog generation: {path}")
