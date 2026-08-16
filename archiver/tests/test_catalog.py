"""Requirements: addresses are normalized and legacy prototype catalogs migrate."""

import sqlite3
from pathlib import Path

from mailarchiver.catalog import create_catalog


def test_migrates_repeated_address_text_to_foreign_keys(tmp_path: Path) -> None:
    path = tmp_path / "archive.sqlite3"
    legacy = sqlite3.connect(path)
    legacy.executescript(
        """
        CREATE TABLE messages (
            message_pk INTEGER PRIMARY KEY, message_id_normalized TEXT NOT NULL, sha256 TEXT NOT NULL,
            sender TEXT NOT NULL, subject TEXT NOT NULL, date_utc TEXT NOT NULL, date_source TEXT NOT NULL,
            category TEXT NOT NULL, UNIQUE(message_id_normalized, sha256)
        );
        CREATE TABLE recipients (message_pk INTEGER NOT NULL, address TEXT NOT NULL, PRIMARY KEY (message_pk, address));
        CREATE TABLE ingest_runs (run_pk INTEGER PRIMARY KEY, started_at TEXT NOT NULL);
        CREATE TABLE observations (observation_pk INTEGER PRIMARY KEY, run_pk INTEGER NOT NULL REFERENCES ingest_runs(run_pk), message_pk INTEGER REFERENCES messages(message_pk), source_path TEXT NOT NULL, disposition TEXT NOT NULL, detail TEXT NOT NULL);
        INSERT INTO ingest_runs VALUES (1, '2020-01-01T00:00:00+00:00');
        INSERT INTO messages VALUES (1, 'one', 'a', 'simsong@acm.org', 'one', '2020-01-01T00:00:00+00:00', 'date', 'Sent');
        INSERT INTO messages VALUES (2, 'two', 'b', 'simsong@acm.org', 'two', '2020-01-02T00:00:00+00:00', 'date', 'Sent');
        INSERT INTO recipients VALUES (1, 'recipient@example.net');
        INSERT INTO recipients VALUES (2, 'recipient@example.net');
        INSERT INTO observations VALUES (1, 1, 1, '/source/one', 'archived', 'Sent');
        """
    )
    legacy.commit()
    legacy.close()

    catalog = create_catalog(path)
    try:
        assert [row[1] for row in catalog.execute("PRAGMA table_info(messages)")] == [
            "message_pk", "message_id_normalized", "sha256", "sender_address_pk", "subject", "date_utc", "date_source", "category"
        ]
        assert [row[1] for row in catalog.execute("PRAGMA table_info(recipients)")] == ["message_pk", "address_pk"]
        assert catalog.execute("SELECT count(*) FROM email_addresses").fetchone() == (2,)
        assert catalog.execute("SELECT count(DISTINCT sender_address_pk) FROM messages").fetchone() == (1,)
        assert catalog.execute("SELECT count(DISTINCT address_pk) FROM recipients").fetchone() == (1,)
        assert catalog.execute("SELECT message_pk FROM observations").fetchone() == (1,)
    finally:
        catalog.close()
