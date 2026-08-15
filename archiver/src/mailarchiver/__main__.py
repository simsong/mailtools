"""Local archive ingestion and review CLI."""

from __future__ import annotations

import argparse
import hashlib
import mailbox
import os
import re
import sqlite3
import subprocess
import tempfile
import time
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from pathlib import Path

from pydantic import BaseModel

CLAMD = "/opt/homebrew/sbin/clamd"
CLAMDSCAN = "/opt/homebrew/bin/clamdscan"
CLAMD_CONFIG = "/opt/homebrew/etc/clamav/clamd.conf"
CLAMD_SOCKET = Path("/private/tmp/clamd.sock")
YEAR = re.compile(r"^(19|20)\d{2}$")


class ParsedMessage(BaseModel):
    """Metadata derived from one raw RFC 5322 message."""

    message_id: str
    sha256: str
    sender: str
    recipients: list[str]
    subject: str
    date_utc: str
    date_source: str
    autosave: bool


class ClamScanner(AbstractContextManager["ClamScanner"]):
    """Use one temporary local clamd process for one ingest run."""

    def __init__(self, mode: str):
        self.mode = mode
        self.process: subprocess.Popen[bytes] | None = None

    def __enter__(self) -> "ClamScanner":
        if self.mode != "on-demand":
            raise ValueError(f"unsupported ClamAV mode: {self.mode}")
        if CLAMD_SOCKET.exists() and self.available():
            return self
        CLAMD_SOCKET.unlink(missing_ok=True)
        self.process = subprocess.Popen(
            [CLAMD, "--foreground", f"--config-file={CLAMD_CONFIG}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(100):
            if CLAMD_SOCKET.exists():
                return self
            if self.process.poll() is not None:
                raise RuntimeError("clamd failed to start; inspect its configuration")
            time.sleep(0.05)
        raise RuntimeError("timed out waiting for clamd socket")

    def __exit__(self, *_: object) -> None:
        if self.process is not None:
            self.process.terminate()
            self.process.wait(timeout=10)
            CLAMD_SOCKET.unlink(missing_ok=True)

    @staticmethod
    def available() -> bool:
        return subprocess.run(
            [CLAMDSCAN, f"--config-file={CLAMD_CONFIG}", "--ping=1"],
            check=False,
            capture_output=True,
        ).returncode == 0

    def infected(self, raw: bytes) -> bool:
        with tempfile.NamedTemporaryFile(prefix="mailarchiver-", delete=False) as handle:
            handle.write(raw)
            temporary = handle.name
        try:
            result = subprocess.run(
                [CLAMDSCAN, f"--config-file={CLAMD_CONFIG}", "--stream", temporary],
                check=False,
                capture_output=True,
            )
            if result.returncode not in (0, 1):
                raise RuntimeError(result.stderr.decode("utf-8", "replace"))
            return result.returncode == 1
        finally:
            os.unlink(temporary)


def create_catalog(path: Path) -> sqlite3.Connection:
    database = sqlite3.connect(path)
    database.executescript(
        """
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS ingest_runs (run_pk INTEGER PRIMARY KEY, started_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS messages (
            message_pk INTEGER PRIMARY KEY, message_id_normalized TEXT NOT NULL, sha256 TEXT NOT NULL,
            sender TEXT NOT NULL, subject TEXT NOT NULL, date_utc TEXT NOT NULL, date_source TEXT NOT NULL,
            category TEXT NOT NULL, UNIQUE(message_id_normalized, sha256)
        );
        CREATE TABLE IF NOT EXISTS observations (
            observation_pk INTEGER PRIMARY KEY, run_pk INTEGER NOT NULL REFERENCES ingest_runs(run_pk),
            message_pk INTEGER REFERENCES messages(message_pk), source_path TEXT NOT NULL,
            disposition TEXT NOT NULL, detail TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS recipients (
            message_pk INTEGER NOT NULL REFERENCES messages(message_pk),
            address TEXT NOT NULL,
            PRIMARY KEY (message_pk, address)
        );
        """
    )
    return database


def create_search(path: Path) -> sqlite3.Connection:
    database = sqlite3.connect(path)
    database.execute("CREATE VIRTUAL TABLE IF NOT EXISTS message_fts USING fts5(sha256 UNINDEXED, content)")
    return database


def parse_date(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if parsed is None:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def path_year(path: Path) -> int | None:
    for part in reversed(path.parts):
        if YEAR.fullmatch(part):
            return int(part)
    return None


def parse_message(raw: bytes, path: Path, prior_date: datetime | None) -> ParsedMessage:
    message = BytesParser(policy=policy.compat32).parsebytes(raw)
    message_id = str(message.get("Message-ID") or "").strip().strip("<>").lower()
    digest = hashlib.sha256(raw).hexdigest()
    if not message_id:
        message_id = digest
    sender = parseaddr(str(message.get("From") or ""))[1].lower()
    recipients = sorted(
        {address.lower() for _, address in getaddresses(message.get_all("To", []) + message.get_all("Cc", []) + message.get_all("Bcc", [])) if address}
    )
    subject = str(message.get("Subject") or "")
    date = parse_date(str(message.get("Date")) if message.get("Date") else None)
    if date is not None:
        date_source = "date"
    elif prior_date is not None:
        date, date_source = prior_date, "previous-message"
    else:
        year = path_year(path)
        if year is None:
            raise ValueError(f"no date or year path fallback for {path}")
        date, date_source = datetime(year, 1, 1, tzinfo=timezone.utc), "path-year"
    return ParsedMessage(
        message_id=message_id,
        sha256=digest,
        sender=sender,
        recipients=recipients,
        subject=subject,
        date_utc=date.isoformat(),
        date_source=date_source,
        autosave=message.get("X-Apple-Auto-Saved") is not None,
    )


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


def source_messages(source: Path) -> list[tuple[Path, bytes]]:
    paths = [source] if source.is_file() else sorted(path for path in source.rglob("*") if path.is_file())
    mboxes = [path for path in paths if path.suffix != ".emlx" and is_mbox(path)]
    emlxs = [path for path in paths if path.suffix == ".emlx"]
    output: list[tuple[Path, bytes]] = []
    for path in mboxes:
        box = mailbox.mbox(path, factory=None, create=False)
        try:
            output.extend((path, box.get_bytes(key, from_=False)) for key in box.iterkeys())
        finally:
            box.close()
    output.extend((path, emlx_bytes(path)) for path in emlxs)
    return output


def owner_tokens(path: Path) -> list[str]:
    return [line.strip().lower() for line in path.read_text().splitlines() if line.strip() and not line.startswith("#")]


def mailbox_name(parsed: ParsedMessage, category: str) -> str:
    if category == "INFECTED":
        return "INFECTED1.mbox"
    return f"{datetime.fromisoformat(parsed.date_utc).year}-{category}1.mbox"


def write_manifests(archive: Path) -> None:
    for mbox_path in archive.glob("*.mbox"):
        digest = hashlib.sha256(mbox_path.read_bytes()).hexdigest()
        mbox_path.with_name(f"{mbox_path.name}.sha256").write_text(f"{digest}  {mbox_path.name}\n")


def ingest(args: argparse.Namespace) -> None:
    archive = Path(args.archive)
    archive.mkdir(parents=True, exist_ok=True)
    catalog, search = create_catalog(archive / "archive.sqlite3"), create_search(archive / "search.sqlite3")
    owners = owner_tokens(Path(args.owner_names_file))
    run_pk = catalog.execute("INSERT INTO ingest_runs(started_at) VALUES (?)", (datetime.now(timezone.utc).isoformat(),)).lastrowid
    boxes: dict[Path, mailbox.mbox] = {}
    prior_dates: dict[Path, datetime] = {}
    try:
        with ClamScanner(args.clamav) as scanner:
            for root in args.roots:
                for path, raw in source_messages(Path(root)):
                    parsed = parse_message(raw, path, prior_dates.get(path))
                    prior_dates[path] = datetime.fromisoformat(parsed.date_utc)
                    if parsed.autosave:
                        catalog.execute("INSERT INTO observations(run_pk, source_path, disposition, detail) VALUES (?, ?, ?, ?)", (run_pk, str(path), "autosave-excluded", "X-Apple-Auto-Saved"))
                        continue
                    existing = catalog.execute("SELECT message_pk FROM messages WHERE message_id_normalized = ? AND sha256 = ?", (parsed.message_id, parsed.sha256)).fetchone()
                    if existing is not None:
                        catalog.execute("INSERT INTO observations(run_pk, message_pk, source_path, disposition, detail) VALUES (?, ?, ?, ?, ?)", (run_pk, existing[0], str(path), "duplicate", "same Message-ID and SHA-256"))
                        continue
                    category = "INFECTED" if scanner.infected(raw) else ("Sent" if any(token in parsed.sender for token in owners) else "Archive")
                    message_pk = catalog.execute("INSERT INTO messages(message_id_normalized, sha256, sender, subject, date_utc, date_source, category) VALUES (?, ?, ?, ?, ?, ?, ?)", (parsed.message_id, parsed.sha256, parsed.sender, parsed.subject, parsed.date_utc, parsed.date_source, category)).lastrowid
                    catalog.executemany("INSERT INTO recipients(message_pk, address) VALUES (?, ?)", ((message_pk, address) for address in parsed.recipients))
                    mbox_path = archive / mailbox_name(parsed, category)
                    box = boxes.get(mbox_path)
                    if box is None:
                        box = mailbox.mbox(mbox_path, create=True)
                        boxes[mbox_path] = box
                    box.add(raw)
                    box.flush()
                    search.execute("INSERT INTO message_fts(sha256, content) VALUES (?, ?)", (parsed.sha256, raw.decode("utf-8", "replace")))
                    catalog.execute("INSERT INTO observations(run_pk, message_pk, source_path, disposition, detail) VALUES (?, ?, ?, ?, ?)", (run_pk, message_pk, str(path), "archived", category))
        catalog.commit()
        search.commit()
    finally:
        for box in boxes.values():
            box.close()
        catalog.close()
        search.close()
    write_manifests(archive)


def review(args: argparse.Namespace) -> None:
    catalog = sqlite3.connect(Path(args.archive) / "archive.sqlite3")
    try:
        query = "SELECT disposition, detail, source_path FROM observations"
        parameters: tuple[int, ...] = () if args.run is None else (args.run,)
        if args.run is not None:
            query += " WHERE run_pk = ?"
        for disposition, detail, path in catalog.execute(query + " ORDER BY observation_pk", parameters):
            print(f"{disposition}\t{detail}\t{path}")
    finally:
        catalog.close()


def report_years(value: str | None) -> tuple[int, int] | None:
    if value is None:
        return None
    match = re.fullmatch(r"(19|20)\d{2}(?:-(19|20)\d{2})?", value)
    if match is None:
        raise ValueError("--year must be YYYY or YYYY-YYYY")
    years = value.split("-")
    return int(years[0]), int(years[-1])


def report(args: argparse.Namespace) -> None:
    years = report_years(args.year)
    catalog = sqlite3.connect(Path(args.archive) / "archive.sqlite3")
    try:
        clause, parameters = ("", ()) if years is None else (" WHERE CAST(substr(date_utc, 1, 4) AS INTEGER) BETWEEN ? AND ?", years)
        rows = catalog.execute(
            "WITH relevant AS (SELECT * FROM messages" + clause + "), "
            "people AS (SELECT substr(date_utc, 1, 4) AS year, sender AS address FROM relevant "
            "UNION SELECT substr(relevant.date_utc, 1, 4), recipients.address FROM recipients "
            "JOIN relevant USING (message_pk)), "
            "summary AS (SELECT substr(date_utc, 1, 4) AS year, SUM(category = 'Sent') AS sent, "
            "SUM(category != 'Sent') AS received FROM relevant GROUP BY year) "
            "SELECT summary.year, sent, received, COUNT(people.address) FROM summary "
            "LEFT JOIN people USING (year) GROUP BY summary.year ORDER BY summary.year",
            parameters,
        )
        print("year\tsent\treceived\tpeople")
        for year, sent, received, people in rows:
            print(f"{year}\t{sent}\t{received}\t{people}")
        if args.top is not None:
            if years is None:
                raise ValueError("--top requires --year")
            print("top senders")
            for address, count in catalog.execute("SELECT sender, COUNT(*) FROM messages" + clause + " GROUP BY sender ORDER BY COUNT(*) DESC, sender LIMIT ?", (*parameters, args.top)):
                print(f"{address}\t{count}")
            print("top recipients")
            for address, count in catalog.execute("SELECT recipients.address, COUNT(*) FROM recipients JOIN messages USING (message_pk)" + clause + " GROUP BY recipients.address ORDER BY COUNT(*) DESC, recipients.address LIMIT ?", (*parameters, args.top)):
                print(f"{address}\t{count}")
    finally:
        catalog.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True, help="canonical archive directory")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest_parser = commands.add_parser("ingest")
    ingest_parser.add_argument("--owner-names-file", required=True)
    ingest_parser.add_argument("--clamav", choices=["on-demand"], required=True)
    ingest_parser.add_argument("roots", nargs="+", metavar="ROOT")
    ingest_parser.set_defaults(function=ingest)
    review_parser = commands.add_parser("review")
    review_parser.add_argument("--run", type=int, help="only show this ingest run's observations")
    review_parser.set_defaults(function=review)
    report_parser = commands.add_parser("report")
    report_parser.add_argument("--year", help="year or inclusive year range, for example 2016 or 2010-2020")
    report_parser.add_argument("--top", type=int, help="show this many top senders and recipients; requires --year")
    report_parser.set_defaults(function=report)
    args = parser.parse_args()
    args.function(args)


if __name__ == "__main__":
    main()
