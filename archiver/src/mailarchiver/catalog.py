"""SQLite catalog and disposable search-index setup."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def create_catalog(path: Path) -> sqlite3.Connection:
    database = sqlite3.connect(path)
    database.executescript(
        """
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS ingest_runs (run_pk INTEGER PRIMARY KEY, started_at TEXT NOT NULL);
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
            disposition TEXT NOT NULL, detail TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS recipients (
            message_pk INTEGER NOT NULL REFERENCES messages(message_pk),
            address_pk INTEGER NOT NULL REFERENCES email_addresses(address_pk),
            PRIMARY KEY (message_pk, address_pk)
        );
        """
    )
    migrate_addresses(database)
    database.executescript(
        """
        CREATE INDEX IF NOT EXISTS messages_sender_address_pk ON messages(sender_address_pk);
        CREATE INDEX IF NOT EXISTS recipients_address_pk ON recipients(address_pk);
        """
    )
    return database


def create_search(path: Path) -> sqlite3.Connection:
    database = sqlite3.connect(path)
    database.execute("CREATE VIRTUAL TABLE IF NOT EXISTS message_fts USING fts5(sha256 UNINDEXED, content)")
    return database


def owner_tokens(path: Path) -> list[str]:
    return [line.strip().lower() for line in path.read_text().splitlines() if line.strip() and not line.startswith("#")]


def address_pk(database: sqlite3.Connection, address: str) -> int:
    database.execute("INSERT INTO email_addresses(address) VALUES (?) ON CONFLICT(address) DO NOTHING", (address,))
    row = database.execute("SELECT address_pk FROM email_addresses WHERE address = ?", (address,)).fetchone()
    assert row is not None
    return int(row[0])


def migrate_addresses(database: sqlite3.Connection) -> None:
    columns = {row[1] for row in database.execute("PRAGMA table_info(messages)")}
    if "sender" not in columns:
        return
    database.execute("PRAGMA foreign_keys = OFF")
    try:
        database.execute("INSERT OR IGNORE INTO email_addresses(address) SELECT DISTINCT sender FROM messages")
        database.execute("INSERT OR IGNORE INTO email_addresses(address) SELECT DISTINCT address FROM recipients")
        database.executescript(
            """
            BEGIN;
            CREATE TABLE messages_new (
                message_pk INTEGER PRIMARY KEY, message_id_normalized TEXT NOT NULL, sha256 TEXT NOT NULL,
                sender_address_pk INTEGER NOT NULL REFERENCES email_addresses(address_pk),
                subject TEXT NOT NULL, date_utc TEXT NOT NULL, date_source TEXT NOT NULL,
                category TEXT NOT NULL, UNIQUE(message_id_normalized, sha256)
            );
            INSERT INTO messages_new
                SELECT messages.message_pk, message_id_normalized, sha256, email_addresses.address_pk,
                       subject, date_utc, date_source, category
                FROM messages JOIN email_addresses ON email_addresses.address = messages.sender;
            CREATE TABLE recipients_new (
                message_pk INTEGER NOT NULL REFERENCES messages_new(message_pk),
                address_pk INTEGER NOT NULL REFERENCES email_addresses(address_pk),
                PRIMARY KEY (message_pk, address_pk)
            );
            INSERT INTO recipients_new
                SELECT recipients.message_pk, email_addresses.address_pk
                FROM recipients JOIN email_addresses ON email_addresses.address = recipients.address;
            DROP TABLE recipients;
            DROP TABLE messages;
            ALTER TABLE messages_new RENAME TO messages;
            ALTER TABLE recipients_new RENAME TO recipients;
            CREATE INDEX messages_sender_address_pk ON messages(sender_address_pk);
            CREATE INDEX recipients_address_pk ON recipients(address_pk);
            COMMIT;
            """
        )
    finally:
        database.execute("PRAGMA foreign_keys = ON")
