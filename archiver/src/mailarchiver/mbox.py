"""Canonical MBOX writes and manifest generation."""

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
        raw = read_location(archive / filename, MboxLocation(byte_offset=offset, byte_length=length))
        if hashlib.sha256(raw).hexdigest() != publication.sha256:
            raise RuntimeError(f"committed pending publication failed validation for {filename}")
        clear_publication_journal(archive)
        return PublicationRecovery.COMMITTED
    path = archive / publication.filename
    if not path.exists() and not publication.file_existed:
        search.execute("DELETE FROM message_fts WHERE sha256 = ?", (publication.sha256,))
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


def read_location(path: Path, location: MboxLocation) -> bytes:
    """Read one mboxrd record directly and restore its RFC 5322 message bytes."""
    with path.open("rb") as source:
        source.seek(location.byte_offset)
        record = source.read(location.byte_length)
    envelope, separator, raw = record.partition(b"\n")
    if not separator or not envelope.startswith(b"From "):
        raise ValueError(f"invalid MBOX location in {path}")
    return raw.replace(b"\n>From ", b"\nFrom ")


def write_manifests(archive: Path) -> None:
    for path in archive.glob("*.mbox"):
        box = mailbox.mbox(path, factory=None, create=False)
        try:
            records = []
            for key in box.iterkeys():
                raw = box.get_bytes(key, from_=False)
                message_id = raw.split(b"\nMessage-ID:", 1)[-1].split(b"\n", 1)[0].strip().decode("utf-8", "replace")
                records.append(f"{message_id}\t{hashlib.sha256(raw).hexdigest()}")
        finally:
            box.close()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        path.with_name(f"{path.name}.sha256").write_text("\n".join([f"sha256\t{digest}", f"messages\t{len(records)}", *records, ""]))
