"""Shared archive-directory command-line configuration."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


MAIL_ARCHIVE_DIR = "MAIL_ARCHIVE_DIR"


def add_archive_argument(parser: argparse.ArgumentParser, description: str) -> None:
    """Add the common archive option, defaulting to the documented environment variable."""
    parser.add_argument(
        "--archive",
        type=Path,
        default=Path(value) if (value := os.environ.get(MAIL_ARCHIVE_DIR)) else None,
        help=f"{description}; defaults to ${MAIL_ARCHIVE_DIR}",
    )


def require_archive(parser: argparse.ArgumentParser, archive: Path | None) -> Path:
    """Return an explicitly supplied or environment-provided archive directory."""
    if archive is None:
        parser.error(f"--archive is required unless ${MAIL_ARCHIVE_DIR} is set")
    return archive
