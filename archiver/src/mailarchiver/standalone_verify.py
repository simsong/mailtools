#!/usr/bin/env python3
"""Generate and verify mailarchiver integrity files using only the stdlib."""

from __future__ import annotations

import argparse
import hashlib
import json
import mailbox
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

BUFFER_SIZE = 1024 * 1024
FORMAT_ID = "tag:simson.net,2026:mailarchiver/integrity"
FORMAT_VERSION = 1
INTEGRITY_SUFFIX = ".integrity"
INSTALLED_NAME = "verify_mail_archive.py"
TABLE_HEADER = "ordinal\tmessage-id-json\thashes..."
CODE_PATTERN = re.compile(r"h[1-9][0-9]*")
HEX_PATTERN = re.compile(r"[0-9a-f]+")
FIELD_NAME_PATTERN = re.compile(rb"[!-9;-~]+")
ALGORITHMS = {"sha256": 64, "sha512": 128}

TYPE = "type"
CODE = "code"
DIGEST_ALGORITHM = "digest_algorithm"
FORMAT_ID_KEY = "format_id"
FORMAT_VERSION_KEY = "format_version"
HASH_STANDARD = "hash_standard"
HASH_VERSION = "hash_version"
ID = "id"
INPUT = "input"
SCOPE = "scope"
CANONICALIZATION = "canonicalization"
SAME_INPUT_AS = "same_input_as"
MANIFEST_ID = "manifest_id"
BYTES = "bytes"
HASHES = "hashes"
MESSAGES = "messages"
NAME = "name"
COLUMNS = "columns"
ENCODING = "encoding"

SEMANTIC_DOMAIN = b"tag:simson.net,2026:mailarchiver/hash/semantic/v1\0"
SEMANTIC_HEADERS = (
    b"from", b"sender", b"reply-to", b"to", b"cc", b"bcc", b"delivered-to",
    b"date", b"message-id", b"subject", b"mime-version", b"content-type",
    b"content-transfer-encoding", b"content-disposition",
)
SEMANTIC_CANONICALIZATION = {
    "body": {"length": "entire", "method": "dkim-simple"},
    "domain_separator": "tag:simson.net,2026:mailarchiver/hash/semantic/v1\0",
    "headers": {
        "method": "dkim-relaxed",
        "occurrences": "all",
        "order": [item.decode("ascii") for item in SEMANTIC_HEADERS],
        "repeated_field_order": "bottom-to-top",
    },
    "line_endings": "crlf-from-crlf-lf-or-cr",
}


@dataclass(frozen=True)
class IntegrityMessage:
    """One message row supplied by the canonical archive catalog."""

    message_id: str | None
    raw_sha256: str
    raw: bytes


@dataclass(frozen=True)
class HashStandard:
    """A validated hash-standard declaration."""

    code: str
    algorithm: str
    standard: str
    version: int
    scope: str
    same_input_as: str | None

    def digest(self, data: bytes) -> str:
        return hashlib.new(self.algorithm, data).hexdigest()


def _json_bytes(value: object) -> bytes:
    encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return f"{encoded}\n".encode("utf-8")


def _normalize_line_endings(raw: bytes) -> bytes:
    return re.sub(rb"\r\n|\r|\n", b"\r\n", raw)


def semantic_bytes(raw: bytes) -> bytes:
    """Return semantic-v1 input bytes using the documented DKIM profile."""
    normalized = _normalize_line_endings(raw)
    header_block, separator, body = normalized.partition(b"\r\n\r\n")
    if not separator:
        body = b""
    fields: list[tuple[bytes, bytes]] = []
    current_name: bytes | None = None
    current_value = b""
    for line in header_block.split(b"\r\n"):
        if line.startswith((b" ", b"\t")) and current_name is not None:
            current_value += b"\r\n" + line
            continue
        if current_name is not None:
            fields.append((current_name, current_value))
            current_name = None
        name, marker, value = line.partition(b":")
        if marker and FIELD_NAME_PATTERN.fullmatch(name):
            current_name, current_value = name.lower(), value
    if current_name is not None:
        fields.append((current_name, current_value))

    output = bytearray(SEMANTIC_DOMAIN)
    for selected in SEMANTIC_HEADERS:
        for name, value in reversed(fields):
            if name == selected:
                unfolded = re.sub(rb"\r\n[ \t]+", b" ", value)
                relaxed = re.sub(rb"[ \t]+", b" ", unfolded).strip(b" \t")
                output.extend(name + b":" + relaxed + b"\r\n")
    output.extend(b"\r\n")
    output.extend(body.rstrip(b"\r\n") + b"\r\n")
    return bytes(output)


def _digest_file(path: Path, algorithms: Iterable[str]) -> dict[str, str]:
    digests = {algorithm: hashlib.new(algorithm) for algorithm in algorithms}
    with path.open("rb") as source:
        for block in iter(lambda: source.read(BUFFER_SIZE), b""):
            for digest in digests.values():
                digest.update(block)
    return {algorithm: digest.hexdigest() for algorithm, digest in digests.items()}


def _standard_records() -> list[dict[str, object]]:
    return [
        {
            CANONICALIZATION: {"method": "none"}, CODE: "h1", DIGEST_ALGORITHM: "sha256",
            HASH_STANDARD: "mbox", HASH_VERSION: 1,
            ID: "tag:simson.net,2026:mailarchiver/hash/mbox/v1/sha256",
            INPUT: "complete-mbox-file", SCOPE: "mbox", TYPE: "hash-standard",
        },
        {
            CANONICALIZATION: {"method": "none"}, CODE: "h2", DIGEST_ALGORITHM: "sha256",
            HASH_STANDARD: "raw", HASH_VERSION: 1,
            ID: "tag:simson.net,2026:mailarchiver/hash/raw/v1/sha256",
            INPUT: "recovered-rfc5322-message", SCOPE: "message", TYPE: "hash-standard",
        },
        {
            CANONICALIZATION: SEMANTIC_CANONICALIZATION, CODE: "h3", DIGEST_ALGORITHM: "sha256",
            HASH_STANDARD: "semantic", HASH_VERSION: 1,
            ID: "tag:simson.net,2026:mailarchiver/hash/semantic/v1/sha256",
            INPUT: "recovered-rfc5322-message", SCOPE: "message", TYPE: "hash-standard",
        },
    ]


def write_integrity_file(mbox_path: Path, messages: Iterable[IntegrityMessage], message_count: int) -> str:
    """Atomically write the current integrity format and return the MBOX SHA-256."""
    initial_stat = mbox_path.stat()
    initial_identity = (
        initial_stat.st_dev, initial_stat.st_ino, initial_stat.st_size,
        initial_stat.st_mtime_ns, initial_stat.st_ctime_ns,
    )
    mbox_sha256 = _digest_file(mbox_path, ("sha256",))["sha256"]
    current = mbox_path.stat()
    if (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns, current.st_ctime_ns) != initial_identity:
        raise ValueError(f"MBOX changed while hashing: {mbox_path}")
    mbox_token = f"h1:{mbox_sha256}"
    records: list[dict[str, object]] = [
        {FORMAT_ID_KEY: FORMAT_ID, FORMAT_VERSION_KEY: FORMAT_VERSION,
         MANIFEST_ID: mbox_token, TYPE: "integrity-manifest"},
        *_standard_records(),
        {BYTES: initial_stat.st_size, HASHES: [mbox_token], MESSAGES: message_count,
         NAME: mbox_path.name, TYPE: "mbox"},
        {COLUMNS: ["ordinal", "message-id-json", "hashes..."], ENCODING: "tsv",
         TYPE: "message-table"},
    ]
    destination = mbox_path.with_name(f"{mbox_path.name}{INTEGRITY_SUFFIX}")
    temporary = destination.with_name(f".{destination.name}.tmp")
    written = 0
    try:
        with temporary.open("wb") as output:
            for record in records:
                output.write(_json_bytes(record))
            output.write(f"{TABLE_HEADER}\n".encode("ascii"))
            for written, message in enumerate(messages, 1):
                actual_raw = hashlib.sha256(message.raw).hexdigest()
                if actual_raw != message.raw_sha256:
                    raise ValueError(f"raw SHA-256 mismatch for message {message.message_id}")
                semantic = hashlib.sha256(semantic_bytes(message.raw)).hexdigest()
                message_id = json.dumps(message.message_id, ensure_ascii=True, separators=(",", ":"))
                output.write(f"{written}\t{message_id}\th2:{actual_raw}\th3:{semantic}\n".encode())
            if written != message_count:
                raise ValueError(f"expected {message_count} messages, received {written}")
            current = mbox_path.stat()
            current_identity = (
                current.st_dev, current.st_ino, current.st_size,
                current.st_mtime_ns, current.st_ctime_ns,
            )
            if current_identity != initial_identity or _digest_file(mbox_path, ("sha256",))["sha256"] != mbox_sha256:
                raise ValueError(f"MBOX changed while writing integrity file: {mbox_path}")
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(destination)
        _sync_directory(destination.parent)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return mbox_sha256


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _load_json(line: bytes) -> dict[str, object]:
    if not line.endswith(b"\n") or line.startswith(b"\xef\xbb\xbf"):
        raise ValueError("control records must be UTF-8 lines terminated by LF")
    def object_hook(pairs: list[tuple[str, object]]) -> dict[str, object]:
        keys = [key for key, _ in pairs]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate JSON object key")
        return dict(pairs)

    value = json.loads(line, object_pairs_hook=object_hook)
    if not isinstance(value, dict):
        raise ValueError("control record must be a JSON object")
    if _json_bytes(value) != line:
        raise ValueError("control record is not deterministically encoded")
    return value


def _parse_standard(record: dict[str, object], prior: list[HashStandard]) -> HashStandard:
    code = record.get(CODE)
    algorithm = record.get(DIGEST_ALGORITHM)
    standard = record.get(HASH_STANDARD)
    version = record.get(HASH_VERSION)
    scope = record.get(SCOPE)
    same_input_as = record.get(SAME_INPUT_AS)
    if code != f"h{len(prior) + 1}" or not isinstance(code, str) or not CODE_PATTERN.fullmatch(code):
        raise ValueError("hash codes must be consecutive h1, h2, ...")
    if algorithm not in ALGORITHMS:
        raise ValueError(f"unsupported digest algorithm for {code}: {algorithm}")
    if standard not in {"mbox", "raw", "semantic"} or version != 1 or scope not in {"mbox", "message"}:
        raise ValueError(f"unsupported hash standard for {code}")
    if scope != ("mbox" if standard == "mbox" else "message"):
        raise ValueError(f"invalid scope for {code}")
    expected_id = f"tag:simson.net,2026:mailarchiver/hash/{standard}/v{version}/{algorithm}"
    if record.get(ID) != expected_id:
        raise ValueError(f"invalid global hash-standard id for {code}")
    expected_input = "complete-mbox-file" if standard == "mbox" else "recovered-rfc5322-message"
    if same_input_as is None:
        expected_canonicalization = SEMANTIC_CANONICALIZATION if standard == "semantic" else {"method": "none"}
        if record.get(INPUT) != expected_input or record.get(CANONICALIZATION) != expected_canonicalization:
            raise ValueError(f"unsupported canonicalization for {code}")
    else:
        referenced = next((item for item in prior if item.code == same_input_as), None)
        if (referenced is None or referenced.same_input_as is not None or referenced.standard != standard
                or referenced.version != version or referenced.scope != scope):
            raise ValueError(f"invalid same_input_as for {code}")
    return HashStandard(code, str(algorithm), str(standard), int(version), str(scope),
                        str(same_input_as) if same_input_as else None)


def _parse_token(token: object, standards: list[HashStandard]) -> tuple[HashStandard, str]:
    if not isinstance(token, str):
        raise ValueError("hash token must be a string")
    code, separator, digest = token.partition(":")
    standard = next((item for item in standards if item.code == code), None)
    if not separator or standard is None or not HEX_PATTERN.fullmatch(digest):
        raise ValueError(f"invalid hash token: {token}")
    if len(digest) != ALGORITHMS[standard.algorithm]:
        raise ValueError(f"wrong digest length for {code}")
    return standard, digest


def _stored_candidates(box: mailbox.mbox, key: object) -> Iterable[bytes]:
    raw = box.get_bytes(key, from_=False)
    lines = raw.splitlines(keepends=True)
    ambiguous = [index for index, line in enumerate(lines) if line.startswith(b">From ")]
    masks = [(1 << len(ambiguous)) - 1, 0]
    if len(ambiguous) <= 12:
        masks.extend(range(1 << len(ambiguous)))
    seen: set[bytes] = set()
    for mask in masks:
        candidate = list(lines)
        for bit, index in enumerate(ambiguous):
            if mask & (1 << bit):
                candidate[index] = candidate[index][1:]
        restored = b"".join(candidate)
        if restored not in seen:
            seen.add(restored)
            yield restored
    if raw == b"\n":
        yield b""


def _check_hashes(tokens: list[str], standards: list[HashStandard], data: bytes) -> list[str]:
    errors: list[str] = []
    parsed = [_parse_token(token, standards) for token in tokens]
    if [standard.code for standard, _ in parsed] != [standard.code for standard in standards]:
        raise ValueError("hash tokens do not match declared codes in order")
    semantic: bytes | None = None
    for standard, expected in parsed:
        if standard.standard == "semantic":
            semantic = semantic if semantic is not None else semantic_bytes(data)
            actual = standard.digest(semantic)
        else:
            actual = standard.digest(data)
        if actual != expected:
            errors.append(f"{standard.code} mismatch: expected {expected}, found {actual}")
    return errors


def verify_mbox(path: Path) -> list[str]:
    integrity = path.with_name(f"{path.name}{INTEGRITY_SUFFIX}")
    if not integrity.is_file():
        return [f"{path.name}: missing integrity file {integrity.name}"]
    try:
        with integrity.open("rb") as source:
            manifest = _load_json(source.readline())
            if (manifest.get(TYPE) != "integrity-manifest" or manifest.get(FORMAT_ID_KEY) != FORMAT_ID
                    or manifest.get(FORMAT_VERSION_KEY) != FORMAT_VERSION):
                raise ValueError("unsupported integrity manifest")
            standards: list[HashStandard] = []
            record = _load_json(source.readline())
            while record.get(TYPE) == "hash-standard":
                standards.append(_parse_standard(record, standards))
                record = _load_json(source.readline())
            required = [("h1", "sha256", "mbox"), ("h2", "sha256", "raw"), ("h3", "sha256", "semantic")]
            if [(item.code, item.algorithm, item.standard) for item in standards[:3]] != required:
                raise ValueError("required h1, h2, and h3 standards are not declared")
            if record.get(TYPE) != "mbox" or record.get(NAME) != path.name:
                raise ValueError("invalid MBOX record")
            mbox_record = record
            table = _load_json(source.readline())
            expected_table = {COLUMNS: ["ordinal", "message-id-json", "hashes..."],
                              ENCODING: "tsv", TYPE: "message-table"}
            if table != expected_table:
                raise ValueError("invalid message-table record")
            if source.readline() != f"{TABLE_HEADER}\n".encode("ascii"):
                raise ValueError("invalid TSV header")

            errors: list[str] = []
            if path.stat().st_size != mbox_record.get(BYTES):
                errors.append(f"{path.name}: byte count mismatch")
            mbox_standards = [item for item in standards if item.scope == "mbox"]
            mbox_tokens = mbox_record.get(HASHES)
            if not isinstance(mbox_tokens, list) or not mbox_tokens:
                raise ValueError("invalid MBOX hashes")
            parsed_mbox = [_parse_token(token, standards) for token in mbox_tokens]
            if [item.code for item, _ in parsed_mbox] != [item.code for item in mbox_standards]:
                raise ValueError("MBOX hashes do not match declared codes")
            file_digests = _digest_file(path, {item.algorithm for item in mbox_standards})
            for standard, expected in parsed_mbox:
                actual = file_digests[standard.algorithm]
                if actual != expected:
                    errors.append(f"{path.name}: {standard.code} mismatch: expected {expected}, found {actual}")
            if manifest.get(MANIFEST_ID) != mbox_tokens[0]:
                raise ValueError("manifest_id is not the primary MBOX hash")

            message_standards = [item for item in standards if item.scope == "message"]
            raw_standards = [item for item in message_standards if item.standard == "raw"]
            if not raw_standards:
                raise ValueError("no raw-message standard declared")
            box = mailbox.mbox(path, factory=None, create=False)
            rows = 0
            try:
                keys = iter(box.iterkeys())
                for rows, line in enumerate(source, 1):
                    if not line.endswith(b"\n"):
                        raise ValueError(f"TSV row {rows} is not LF terminated")
                    fields = line[:-1].decode("utf-8").split("\t")
                    if len(fields) != 2 + len(message_standards) or fields[0] != str(rows):
                        raise ValueError(f"invalid TSV message row {rows}")
                    message_id = json.loads(fields[1])
                    if message_id is not None and not isinstance(message_id, str):
                        raise ValueError(f"invalid message-id-json in row {rows}")
                    if json.dumps(message_id, ensure_ascii=True, separators=(",", ":")) != fields[1]:
                        raise ValueError(f"message-id-json is not deterministically encoded in row {rows}")
                    parsed = [_parse_token(token, standards) for token in fields[2:]]
                    if [item.code for item, _ in parsed] != [item.code for item in message_standards]:
                        raise ValueError(f"message hashes do not match declared codes in row {rows}")
                    try:
                        key = next(keys)
                    except StopIteration:
                        errors.append(f"{path.name}: sidecar contains more messages than MBOX")
                        break
                    expected_raw = {item.code: digest for item, digest in parsed if item.standard == "raw"}
                    candidate = next((raw for raw in _stored_candidates(box, key)
                                      if all(item.digest(raw) == expected_raw[item.code]
                                             for item in raw_standards)), None)
                    if candidate is None:
                        errors.append(f"{path.name}: message {rows} raw hash mismatch")
                        continue
                    for detail in _check_hashes(fields[2:], message_standards, candidate):
                        errors.append(f"{path.name}: message {rows} {detail}")
                if next(keys, None) is not None:
                    errors.append(f"{path.name}: MBOX contains more messages than sidecar")
            finally:
                box.close()
            if rows != mbox_record.get(MESSAGES):
                errors.append(f"{path.name}: message count mismatch")
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError, mailbox.Error) as error:
        return [f"{integrity.name}: {error}"]
    if not errors:
        print(f"OK {path.name}: {rows} messages")
    return errors


def verify_archive(archive: Path) -> list[str]:
    mailboxes = sorted(archive.glob("*.mbox"))
    errors = [] if mailboxes else [f"{archive}: no .mbox files found"]
    for path in mailboxes:
        errors.extend(verify_mbox(path))
    mailbox_names = {path.name for path in mailboxes}
    for integrity in sorted(archive.glob(f"*.mbox{INTEGRITY_SUFFIX}")):
        if integrity.name.removesuffix(INTEGRITY_SUFFIX) not in mailbox_names:
            errors.append(f"{integrity.name}: integrity file has no MBOX file")
    return errors


def install_archive_verifier(archive: Path) -> Path:
    """Install this dependency-free source file in an archive atomically."""
    source = Path(__file__).read_bytes()
    destination = archive / INSTALLED_NAME
    if destination.is_file() and destination.read_bytes() == source:
        return destination
    temporary = archive / f".{INSTALLED_NAME}.tmp"
    temporary.write_bytes(source)
    os.chmod(temporary, 0o755)
    temporary.replace(destination)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify every integrity digest in a mailarchiver archive.")
    parser.add_argument("archive", nargs="?", type=Path, default=Path(__file__).resolve().parent)
    archive = parser.parse_args().archive
    if not archive.is_dir():
        parser.error(f"not a directory: {archive}")
    errors = verify_archive(archive)
    for error in errors:
        print(f"ERROR {error}", file=sys.stderr)
    if errors:
        print(f"FAILED: {len(errors)} integrity error(s)", file=sys.stderr)
        return 1
    print("Archive integrity verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
