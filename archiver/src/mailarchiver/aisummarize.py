"""Summarize standard input with Apple's on-device Foundation Models framework."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

SWIFT_SOURCE = Path(__file__).with_name("apple_summary.swift")
CACHE_DIRECTORY = Path.home() / "Library" / "Caches" / "mailarchiver"


def helper_path() -> Path:
    """Return the content-addressed native helper path, compiling it when absent."""
    digest = hashlib.sha256(SWIFT_SOURCE.read_bytes()).hexdigest()[:16]
    return CACHE_DIRECTORY / f"aisummarize-{digest}"


def build_helper(destination: Path) -> None:
    CACHE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    command = [
        "/usr/bin/xcrun",
        "swiftc",
        "-parse-as-library",
        "-O",
        "-framework",
        "FoundationModels",
        "-framework",
        "Foundation",
        "-o",
        str(temporary),
        str(SWIFT_SOURCE),
    ]
    try:
        completed = subprocess.run(command, check=False)
        if completed.returncode:
            raise RuntimeError("could not compile the Apple Foundation Models helper")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    source_text = sys.stdin.read()
    if not source_text.strip():
        print("summarize: standard input is empty", file=sys.stderr)
        return 2
    helper = helper_path()
    if not helper.is_file():
        try:
            build_helper(helper)
        except (OSError, RuntimeError) as error:
            print(f"summarize: {error}", file=sys.stderr)
            return 1
    try:
        completed = subprocess.run([str(helper)], input=source_text, text=True, check=False)
    except OSError as error:
        print(f"summarize: could not run Apple Foundation Models helper: {error}", file=sys.stderr)
        return 1
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
