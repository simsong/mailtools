"""Read-only streaming adapters for local message sources."""

from __future__ import annotations

import hashlib
import mailbox
import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Literal

from pydantic import BaseModel


class SourceMessage(BaseModel):
    path: Path
    raw: bytes
    source_offset: int
    bytes_done: int
    bytes_total: int


class SourceFile(BaseModel):
    path: Path
    kind: Literal["emlx", "mbox", "message"]
    modified_at_ns: int
    byte_length: int


class SourcePlan(BaseModel):
    source: SourceFile
    sha256: str | None = None
    start_offset: int = 0
    skip: bool = False


class SourceHashes(BaseModel):
    prefix_sha256: str
    sha256: str


class IncompleteAppleMailMessageError(ValueError):
    """An Apple Mail partial message cannot preserve detached attachment bytes."""


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


def source_files(source: Path) -> Iterator[SourceFile]:
    if not source.exists():
        raise FileNotFoundError(source)
    if source.is_file():
        paths: Iterator[Path] = iter((source,))
    else:
        def raise_walk_error(error: OSError) -> None:
            raise error

        paths = (
            Path(directory) / filename
            for directory, _subdirectories, filenames in os.walk(source, onerror=raise_walk_error)
            for filename in filenames
        )
    for path in paths:
        path = path.resolve()
        kind: Literal["emlx", "mbox", "message"] | None = None
        if path.name.lower().endswith(".partial.emlx"):
            raise IncompleteAppleMailMessageError(
                f"Apple Mail partial message omits detached attachment bytes: {path}; "
                "export the mailbox from Apple Mail before ingest"
            )
        if path.suffix.lower() == ".emlx":
            kind = "emlx"
        elif is_mbox(path):
            kind = "mbox"
        elif path.suffix.lower() == ".eml" or is_maildir_message(path):
            kind = "message"
        if kind is not None:
            stat = path.stat()
            yield SourceFile(path=path, kind=kind, modified_at_ns=stat.st_mtime_ns, byte_length=stat.st_size)


def source_messages(source: SourceFile, start_offset: int = 0) -> Iterator[SourceMessage]:
    path = source.path
    if source.kind == "emlx":
        raw = emlx_bytes(path)
        yield SourceMessage(path=path, raw=raw, source_offset=0, bytes_done=source.byte_length, bytes_total=source.byte_length)
    elif source.kind == "mbox":
        box = mailbox.mbox(path, factory=None, create=False)
        try:
            for key in box.iterkeys():
                start, end = box._toc[key]
                if start >= start_offset:
                    yield SourceMessage(path=path, raw=box.get_bytes(key, from_=False), source_offset=start, bytes_done=end, bytes_total=source.byte_length)
        finally:
            box.close()
    else:
        raw = path.read_bytes()
        yield SourceMessage(path=path, raw=raw, source_offset=0, bytes_done=len(raw), bytes_total=len(raw))


def sha256_file(path: Path, progress: Callable[[int, int], None] | None = None) -> str:
    total = path.stat().st_size
    remaining = total
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while remaining:
            block = source.read(min(1024 * 1024, remaining))
            if not block:
                raise ValueError(f"source shortened while hashing: {path}")
            digest.update(block)
            remaining -= len(block)
            if progress is not None:
                progress(total - remaining, total)
    return digest.hexdigest()


def sha256_file_with_prefix(
    path: Path, prefix_length: int, progress: Callable[[int, int], None] | None = None
) -> SourceHashes:
    total = path.stat().st_size
    if not 0 <= prefix_length <= total:
        raise ValueError(f"invalid prefix length for {path}: {prefix_length}")
    digest = hashlib.sha256()
    prefix_sha256 = digest.hexdigest() if prefix_length == 0 else ""
    done = 0
    with path.open("rb") as source:
        while done < total:
            boundary = prefix_length if done < prefix_length else total
            block = source.read(min(1024 * 1024, boundary - done))
            if not block:
                raise ValueError(f"source shortened while hashing: {path}")
            digest.update(block)
            done += len(block)
            if done == prefix_length:
                prefix_sha256 = digest.copy().hexdigest()
            if progress is not None:
                progress(done, total)
    return SourceHashes(prefix_sha256=prefix_sha256, sha256=digest.hexdigest())


def has_mbox_append_boundary(path: Path, offset: int) -> bool:
    with path.open("rb") as source:
        source.seek(offset)
        return source.read(5) == b"From "
