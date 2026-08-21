"""Requirements: fresh catalogs are versioned and legacy schemas are not migrated."""

import sqlite3
from pathlib import Path

import pytest

from mailarchiver.catalog import SCHEMA_VERSION, create_catalog


def test_rejects_unversioned_catalog(tmp_path: Path) -> None:
    path = tmp_path / "archive.sqlite3"
    legacy = sqlite3.connect(path)
    legacy.executescript(
        """
        CREATE TABLE messages (message_pk INTEGER PRIMARY KEY);
        """
    )
    legacy.commit()
    legacy.close()

    with pytest.raises(RuntimeError, match="unsupported unversioned"):
        create_catalog(path)


def test_creates_current_schema_without_migration(tmp_path: Path) -> None:
    catalog = create_catalog(tmp_path / "archive.sqlite3")
    try:
        assert catalog.execute("SELECT version FROM schema_info").fetchone() == (SCHEMA_VERSION,)
        tables = {row[0] for row in catalog.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert {"source_files", "metadata_defects"} <= tables
    finally:
        catalog.close()
