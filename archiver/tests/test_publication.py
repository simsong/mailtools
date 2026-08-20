"""Requirement: incomplete MBOX/catalog/search publication is rolled back on recovery."""

import hashlib
import mailbox
from pathlib import Path

from mailarchiver.catalog import create_catalog, create_search
from mailarchiver.mbox import PendingPublication, PublicationRecovery, add_message, journal_publication, recover_publication


def test_recovery_truncates_orphaned_mbox_append_and_search_row(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    path = archive / "2024-Archive1.mbox"
    box = mailbox.mbox(path, create=True)
    try:
        original = b"Message-ID: <original@example>\n\noriginal\n"
        orphan = b"Message-ID: <orphan@example>\n\norphan\n"
        add_message(box, path, original)
        prior_size = path.stat().st_size
        add_message(box, path, orphan)
    finally:
        box.close()
    journal_publication(
        archive,
        PendingPublication(
            filename=path.name,
            prior_size=prior_size,
            file_existed=True,
            message_id="orphan@example",
            sha256="orphan-sha256",
        ),
    )
    catalog = create_catalog(archive / "archive.sqlite3")
    search = create_search(archive / "search.sqlite3")
    search.execute("INSERT INTO message_fts(sha256, content) VALUES (?, ?)", ("orphan-sha256", "orphan"))
    search.commit()

    try:
        assert recover_publication(archive, catalog, search) is PublicationRecovery.ROLLED_BACK
        assert path.stat().st_size == prior_size
        assert search.execute("SELECT count(*) FROM message_fts WHERE sha256 = ?", ("orphan-sha256",)).fetchone() == (0,)
        assert not (archive / ".mailarchiver-pending.json").exists()
    finally:
        catalog.close()
        search.close()
    recovered = mailbox.mbox(path, factory=None, create=False)
    try:
        assert [recovered.get_bytes(key, from_=False) for key in recovered.iterkeys()] == [original]
    finally:
        recovered.close()


def test_recovery_keeps_catalogued_mbox_append(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    path = archive / "2024-Archive1.mbox"
    raw = b"Message-ID: <committed@example>\n\ncommitted\n"
    digest = hashlib.sha256(raw).hexdigest()
    box = mailbox.mbox(path, create=True)
    try:
        location = add_message(box, path, raw)
    finally:
        box.close()
    journal_publication(
        archive,
        PendingPublication(
            filename=path.name,
            prior_size=0,
            file_existed=False,
            message_id="committed@example",
            sha256=digest,
        ),
    )
    catalog = create_catalog(archive / "archive.sqlite3")
    search = create_search(archive / "search.sqlite3")
    catalog.execute("INSERT INTO email_addresses(address) VALUES ('sender@example.net')")
    catalog.execute(
        "INSERT INTO messages(message_id_normalized, sha256, sender_address_pk, subject, date_utc, date_source, category) "
        "VALUES (?, ?, 1, '', '2024-01-01T00:00:00+00:00', 'date', 'Archive')",
        ("committed@example", digest),
    )
    generation_pk = catalog.execute(
        "INSERT INTO mbox_generations(filename, sha256, message_count, byte_count) VALUES (?, '', 1, ?)",
        (path.name, path.stat().st_size),
    ).lastrowid
    catalog.execute(
        "INSERT INTO locations(message_pk, generation_pk, byte_offset, byte_length) VALUES (1, ?, ?, ?)",
        (generation_pk, location.byte_offset, location.byte_length),
    )
    catalog.commit()
    search.execute("INSERT INTO message_fts(sha256, content) VALUES (?, 'committed')", (digest,))
    search.commit()

    try:
        assert recover_publication(archive, catalog, search) is PublicationRecovery.COMMITTED
        assert not (archive / ".mailarchiver-pending.json").exists()
    finally:
        catalog.close()
        search.close()
    recovered = mailbox.mbox(path, factory=None, create=False)
    try:
        assert [recovered.get_bytes(key, from_=False) for key in recovered.iterkeys()] == [raw]
    finally:
        recovered.close()
