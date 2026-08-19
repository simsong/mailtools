"""Canonical MBOX writes and manifest generation."""

from __future__ import annotations

import errno
import hashlib
import mailbox
import shutil
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from .message import ParsedMessage


class DiskFullError(RuntimeError):
    """The archive cannot safely accept another message."""


class MboxLocation(BaseModel):
    byte_offset: int
    byte_length: int


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
