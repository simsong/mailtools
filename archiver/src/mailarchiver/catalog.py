"""SQLite catalog and disposable search-index setup."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1


def create_catalog(path: Path) -> sqlite3.Connection:
    database = sqlite3.connect(path)
    tables = {row[0] for row in database.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if tables and "schema_info" not in tables:
        database.close()
        raise RuntimeError("unsupported unversioned archive database; use a new empty archive directory")
    if "schema_info" in tables:
        version = database.execute("SELECT version FROM schema_info").fetchone()
        if version != (SCHEMA_VERSION,):
            database.close()
            raise RuntimeError(f"unsupported archive database schema {version}; expected {SCHEMA_VERSION}")
    database.executescript(
        f"""
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS schema_info (version INTEGER NOT NULL);
        INSERT INTO schema_info(version) SELECT {SCHEMA_VERSION} WHERE NOT EXISTS (SELECT 1 FROM schema_info);
        CREATE TABLE IF NOT EXISTS ingest_runs (
            run_pk INTEGER PRIMARY KEY, started_at TEXT NOT NULL,
            completed_at TEXT, result TEXT, detail TEXT
        );
        CREATE TABLE IF NOT EXISTS email_addresses (
            address_pk INTEGER PRIMARY KEY, address TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS messages (
            message_pk INTEGER PRIMARY KEY, message_id_normalized TEXT NOT NULL, sha256 TEXT NOT NULL,
            sender_address_pk INTEGER NOT NULL REFERENCES email_addresses(address_pk),
            subject TEXT NOT NULL, date_utc TEXT NOT NULL, date_source TEXT NOT NULL,
            category TEXT NOT NULL, UNIQUE(message_id_normalized, sha256)
        );
        CREATE TABLE IF NOT EXISTS observations (
            observation_pk INTEGER PRIMARY KEY, run_pk INTEGER NOT NULL REFERENCES ingest_runs(run_pk),
            message_pk INTEGER REFERENCES messages(message_pk), source_path TEXT NOT NULL,
            source_offset INTEGER NOT NULL DEFAULT 0, source_sha256 TEXT NOT NULL DEFAULT '',
            disposition TEXT NOT NULL, detail TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS source_files (
            source_path TEXT PRIMARY KEY,
            modified_at_ns INTEGER NOT NULL,
            byte_length INTEGER NOT NULL,
            sha256 TEXT NOT NULL,
            checked_at TEXT NOT NULL,
            completed_run INTEGER NOT NULL REFERENCES ingest_runs(run_pk)
        );
        CREATE TABLE IF NOT EXISTS metadata_defects (
            message_pk INTEGER NOT NULL REFERENCES messages(message_pk),
            field TEXT NOT NULL,
            detail TEXT NOT NULL,
            PRIMARY KEY (message_pk, field, detail)
        );
        CREATE TABLE IF NOT EXISTS recipients (
            message_pk INTEGER NOT NULL REFERENCES messages(message_pk),
            address_pk INTEGER NOT NULL REFERENCES email_addresses(address_pk),
            PRIMARY KEY (message_pk, address_pk)
        );
        CREATE TABLE IF NOT EXISTS mbox_generations (
            generation_pk INTEGER PRIMARY KEY,
            filename TEXT NOT NULL UNIQUE,
            sha256 TEXT NOT NULL,
            message_count INTEGER NOT NULL,
            byte_count INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS locations (
            message_pk INTEGER PRIMARY KEY REFERENCES messages(message_pk),
            generation_pk INTEGER NOT NULL REFERENCES mbox_generations(generation_pk),
            byte_offset INTEGER NOT NULL,
            byte_length INTEGER NOT NULL
        );
        """
    )
    database.executescript(
        """
        CREATE INDEX IF NOT EXISTS messages_sender_address_pk ON messages(sender_address_pk);
        CREATE INDEX IF NOT EXISTS recipients_address_pk ON recipients(address_pk);
        CREATE INDEX IF NOT EXISTS locations_generation_pk ON locations(generation_pk);
        """
    )
    return database


def create_search(path: Path) -> sqlite3.Connection:
    database = sqlite3.connect(path)
    database.execute("CREATE VIRTUAL TABLE IF NOT EXISTS message_fts USING fts5(sha256 UNINDEXED, content)")
    database.execute("CREATE VIRTUAL TABLE IF NOT EXISTS attachment_fts USING fts5(sha256 UNINDEXED, content)")
    database.executescript(
        """
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS message_metadata (
            sha256 TEXT PRIMARY KEY,
            attachment_count INTEGER NOT NULL CHECK (attachment_count >= 0),
            preview TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS message_attachments (
            sha256 TEXT NOT NULL REFERENCES message_metadata(sha256) ON DELETE CASCADE,
            attachment_ordinal INTEGER NOT NULL CHECK (attachment_ordinal > 0),
            part_id INTEGER NOT NULL CHECK (part_id >= 0),
            filename TEXT NOT NULL,
            mime_type TEXT NOT NULL,
            PRIMARY KEY (sha256, attachment_ordinal)
        );
        CREATE INDEX IF NOT EXISTS message_attachments_mime_type ON message_attachments(mime_type);
        """
    )
    return database


def owner_tokens(path: Path) -> list[str]:
    return [line.strip().lower() for line in path.read_text().splitlines() if line.strip() and not line.startswith("#")]


def address_pk(database: sqlite3.Connection, address: str) -> int:
    database.execute("INSERT INTO email_addresses(address) VALUES (?) ON CONFLICT(address) DO NOTHING", (address,))
    row = database.execute("SELECT address_pk FROM email_addresses WHERE address = ?", (address,)).fetchone()
    assert row is not None
    return int(row[0])
