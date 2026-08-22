"""Requirements: fresh catalogs are versioned and incompatible schemas fail closed."""

import sqlite3
from pathlib import Path

import pytest

from mailarchiver.catalog import SCHEMA_VERSION, create_catalog


def test_rejects_unversioned_catalog(tmp_path: Path) -> None:
    path = tmp_path / "archive.sqlite3"
    incompatible = sqlite3.connect(path)
    incompatible.executescript(
        """
        CREATE TABLE messages (message_pk INTEGER PRIMARY KEY);
        """
    )
    incompatible.commit()
    incompatible.close()

    with pytest.raises(RuntimeError, match="unsupported unversioned"):
        create_catalog(path)


def test_creates_current_schema_directly(tmp_path: Path) -> None:
    catalog = create_catalog(tmp_path / "archive.sqlite3")
    try:
        assert catalog.execute("SELECT version FROM schema_info").fetchone() == (SCHEMA_VERSION,)
        tables = {row[0] for row in catalog.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert {"source_files", "metadata_defects"} <= tables
    finally:
        catalog.close()
