"""Read-only streaming adapters for local message sources."""

from __future__ import annotations

import mailbox
from collections.abc import Iterator
from pathlib import Path

from pydantic import BaseModel


class SourceMessage(BaseModel):
    path: Path
    raw: bytes
    bytes_done: int
    bytes_total: int


def emlx_bytes(path: Path) -> bytes:
    with path.open("rb") as source:
        length = int(source.readline().strip())
        raw = source.read(length)
    if len(raw) != length:
        raise ValueError(f"truncated emlx message: {path}")
    return raw


def is_mbox(path: Path) -> bool:
    with path.open("rb") as source:
        return source.read(5) == b"From "


def is_maildir_message(path: Path) -> bool:
    return path.parent.name in {"cur", "new"}


def source_messages(source: Path) -> Iterator[SourceMessage]:
    paths = (source,) if source.is_file() else (path for path in source.rglob("*") if path.is_file())
    for path in paths:
        if path.suffix == ".emlx":
            raw = emlx_bytes(path)
            yield SourceMessage(path=path, raw=raw, bytes_done=path.stat().st_size, bytes_total=path.stat().st_size)
        elif is_mbox(path):
            box = mailbox.mbox(path, factory=None, create=False)
            try:
                for key in box.iterkeys():
                    _, end = box._toc[key]
                    yield SourceMessage(path=path, raw=box.get_bytes(key, from_=False), bytes_done=end, bytes_total=path.stat().st_size)
            finally:
                box.close()
        elif path.suffix.lower() == ".eml" or is_maildir_message(path):
            raw = path.read_bytes()
            yield SourceMessage(path=path, raw=raw, bytes_done=len(raw), bytes_total=len(raw))
