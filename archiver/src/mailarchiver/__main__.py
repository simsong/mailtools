"""Local archive ingestion and review CLI."""

from __future__ import annotations

import argparse
import os
import mailbox
import re
import sqlite3
import sys
import threading
import time
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from .catalog import address_pk, create_catalog, create_search, owner_tokens
from .message import ParsedMessage, parse_message
from .mbox import DiskFullError, add_message, mailbox_name, write_manifests
from .scanner import ClamScanner
from .search import index_message
from .sources import SourceMessage, source_messages

DEFAULT_REPORT_TOP = 10


class YearProgress(BaseModel):
    year: int
    messages: int = 0


class IngestCounts(BaseModel):
    archived: int = 0
    duplicates: int = 0
    autosaves: int = 0
    infected: int = 0


class PendingScan(BaseModel):
    source: SourceMessage
    parsed: ParsedMessage


class ProgressState(BaseModel):
    started_at: datetime
    started_monotonic: float
    processed: int = 0
    earliest_date: datetime | None = None
    latest_date: datetime | None = None
    current_year: int | None = None
    current_year_messages: int = 0
    current_file: str | None = None
    file_bytes_done: int = 0
    file_bytes_total: int = 0
    counts: IngestCounts = IngestCounts()
    years: list[YearProgress] = []


class ProgressReporter:
    """Print a thread-safe ingest heartbeat without delaying message handling."""

    def __init__(self) -> None:
        self.state = ProgressState(started_at=datetime.now(timezone.utc), started_monotonic=time.monotonic())
        self.lock = threading.Lock()
        self.done = threading.Event()
        self.thread = threading.Thread(target=self.heartbeat, daemon=True)
        self.tty = sys.stderr.isatty()
        self.rendered = False

    def start(self) -> None:
        self.display("started")
        self.thread.start()

    def record(self, parsed: ParsedMessage, source: SourceMessage) -> None:
        date = datetime.fromisoformat(parsed.date_utc)
        with self.lock:
            self.state.processed += 1
            self.state.earliest_date = date if self.state.earliest_date is None else min(self.state.earliest_date, date)
            self.state.latest_date = date if self.state.latest_date is None else max(self.state.latest_date, date)
            year = date.year
            progress = next((entry for entry in self.state.years if entry.year == year), None)
            if progress is None:
                progress = YearProgress(year=year)
                self.state.years.append(progress)
            progress.messages += 1
            self.state.current_year = year
            self.state.current_year_messages = progress.messages
            self.state.current_file = str(source.path)
            self.state.file_bytes_done = source.bytes_done
            self.state.file_bytes_total = source.bytes_total

    def record_disposition(self, disposition: str) -> None:
        with self.lock:
            if disposition == "archived":
                self.state.counts.archived += 1
            elif disposition == "duplicate":
                self.state.counts.duplicates += 1
            elif disposition == "autosave-excluded":
                self.state.counts.autosaves += 1
            elif disposition == "infected":
                self.state.counts.infected += 1

    def heartbeat(self) -> None:
        while not self.done.wait(2):
            self.display("progress")

    def display(self, label: str) -> None:
        with self.lock:
            state = self.state.model_copy(deep=True)
        elapsed = max(time.monotonic() - state.started_monotonic, 0.001)
        dates = "none" if state.earliest_date is None else f"{state.earliest_date.date()}..{state.latest_date.date()}"
        year = "none" if state.current_year is None else str(state.current_year)
        percent = 0 if state.file_bytes_total == 0 else 100 * state.file_bytes_done / state.file_bytes_total
        current = "waiting for source" if state.current_file is None else f"{state.current_file} ({percent:.1f}%)"
        if self.tty:
            lines = [
                f"mailarchiver ingest  [{label}]",
                f"Processed: {state.processed:,}  Rate: {state.processed / elapsed:.2f} messages/s  Elapsed: {elapsed:.0f}s",
                f"Current:   {current}",
                f"Dates:     {dates}  Current year: {year} ({state.current_year_messages:,} messages)",
                f"Archived:  {state.counts.archived:,}  Seen/skipped: {state.counts.duplicates:,}  Autosaved: {state.counts.autosaves:,}  Infected: {state.counts.infected:,}",
            ]
            sys.stderr.write(("\x1b[5A" if self.rendered else "") + "\n".join(f"\r\x1b[2K{line}" for line in lines) + "\n")
            self.rendered = True
        else:
            print(
                f"{label}: processed={state.processed} rate={state.processed / elapsed:.2f}/s "
                f"file={current} dates={dates} current_year={year} year_messages={state.current_year_messages} "
                f"archived={state.counts.archived} seen_skipped={state.counts.duplicates} "
                f"autosaved={state.counts.autosaves} infected={state.counts.infected}",
                file=sys.stderr,
            )
        sys.stderr.flush()

    def finish(self, status: str) -> None:
        self.done.set()
        self.thread.join()
        self.display(status)


def ingest(args: argparse.Namespace) -> None:
    archive = Path(args.archive)
    archive.mkdir(parents=True, exist_ok=True)
    catalog, search = create_catalog(archive / "archive.sqlite3"), create_search(archive / "search.sqlite3")
    owners = owner_tokens(Path(args.owner_names_file))
    run_pk = catalog.execute("INSERT INTO ingest_runs(started_at) VALUES (?)", (datetime.now(timezone.utc).isoformat(),)).lastrowid
    boxes: dict[Path, mailbox.mbox] = {}
    prior_dates: dict[Path, datetime] = {}
    pending_identities: set[tuple[str, str]] = set()
    progress = ProgressReporter()
    succeeded = False
    interrupted = False
    disk_full = False
    progress.start()

    def archive_scanned(candidate: PendingScan, infected: bool) -> None:
        path, raw, parsed = candidate.source.path, candidate.source.raw, candidate.parsed
        category = "INFECTED" if infected else ("Sent" if any(token in parsed.sender for token in owners) else "Archive")
        sender_pk = address_pk(catalog, parsed.sender)
        message_pk = catalog.execute("INSERT INTO messages(message_id_normalized, sha256, sender_address_pk, subject, date_utc, date_source, category) VALUES (?, ?, ?, ?, ?, ?, ?)", (parsed.message_id, parsed.sha256, sender_pk, parsed.subject, parsed.date_utc, parsed.date_source, category)).lastrowid
        catalog.executemany("INSERT INTO recipients(message_pk, address_pk) VALUES (?, ?)", ((message_pk, address_pk(catalog, address)) for address in parsed.recipients))
        mbox_path = archive / mailbox_name(parsed, category)
        box = boxes.get(mbox_path)
        if box is None:
            box = mailbox.mbox(mbox_path, create=True)
            boxes[mbox_path] = box
        add_message(box, mbox_path, raw)
        index_message(search, raw, args.index_attachments)
        catalog.execute("INSERT INTO observations(run_pk, message_pk, source_path, disposition, detail) VALUES (?, ?, ?, ?, ?)", (run_pk, message_pk, str(path), "archived", category))
        catalog.commit()
        search.commit()
        progress.record_disposition("archived")
        if category == "INFECTED":
            progress.record_disposition("infected")

    try:
        with ClamScanner() as scanner, ThreadPoolExecutor(max_workers=args.workers) as workers:
            pending: deque[tuple[PendingScan, Future[bool]]] = deque()
            for root in args.roots:
                for source in source_messages(Path(root)):
                    path, raw = source.path, source.raw
                    parsed = parse_message(raw, path, prior_dates.get(path))
                    prior_dates[path] = datetime.fromisoformat(parsed.date_utc)
                    progress.record(parsed, source)
                    if parsed.autosave:
                        catalog.execute("INSERT INTO observations(run_pk, source_path, disposition, detail) VALUES (?, ?, ?, ?)", (run_pk, str(path), "autosave-excluded", "X-Apple-Auto-Saved"))
                        catalog.commit()
                        progress.record_disposition("autosave-excluded")
                        continue
                    identity = (parsed.message_id, parsed.sha256)
                    existing = catalog.execute("SELECT message_pk FROM messages WHERE message_id_normalized = ? AND sha256 = ?", identity).fetchone()
                    if existing is not None or identity in pending_identities:
                        message_pk = None if existing is None else existing[0]
                        detail = "same Message-ID and SHA-256" if existing is not None else "same Message-ID and SHA-256 pending scan"
                        catalog.execute("INSERT INTO observations(run_pk, message_pk, source_path, disposition, detail) VALUES (?, ?, ?, ?, ?)", (run_pk, message_pk, str(path), "duplicate", detail))
                        catalog.commit()
                        progress.record_disposition("duplicate")
                        continue
                    candidate = PendingScan(source=source, parsed=parsed)
                    pending_identities.add(identity)
                    pending.append((candidate, workers.submit(scanner.infected, raw)))
                    if len(pending) >= args.workers * 2:
                        completed, future = pending.popleft()
                        archive_scanned(completed, future.result())
                        pending_identities.remove((completed.parsed.message_id, completed.parsed.sha256))
            while pending:
                completed, future = pending.popleft()
                archive_scanned(completed, future.result())
                pending_identities.remove((completed.parsed.message_id, completed.parsed.sha256))
        catalog.commit()
        search.commit()
        succeeded = True
    except KeyboardInterrupt:
        interrupted = True
        catalog.commit()
        search.commit()
        raise
    except DiskFullError:
        disk_full = True
        raise
    finally:
        for box in boxes.values():
            box.close()
        catalog.close()
        search.close()
        if succeeded or interrupted:
            write_manifests(archive)
        progress.finish("completed" if succeeded else "interrupted" if interrupted else "disk-full" if disk_full else "failed")


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


def print_report(archive: Path, years: tuple[int, int] | None, top: int | None) -> None:
    catalog = sqlite3.connect(archive / "archive.sqlite3")
    try:
        clause, parameters = ("", ()) if years is None else (" WHERE CAST(substr(date_utc, 1, 4) AS INTEGER) BETWEEN ? AND ?", years)
        rows = catalog.execute(
            "WITH relevant AS (SELECT * FROM messages" + clause + "), "
            "people AS (SELECT substr(relevant.date_utc, 1, 4) AS year, email_addresses.address "
            "FROM relevant JOIN email_addresses ON email_addresses.address_pk = relevant.sender_address_pk "
            "UNION SELECT substr(relevant.date_utc, 1, 4), email_addresses.address FROM recipients "
            "JOIN relevant USING (message_pk) JOIN email_addresses USING (address_pk)), "
            "summary AS (SELECT substr(date_utc, 1, 4) AS year, SUM(category = 'Sent') AS sent, "
            "SUM(category != 'Sent') AS received FROM relevant GROUP BY year) "
            "SELECT summary.year, sent, received, COUNT(people.address) FROM summary "
            "LEFT JOIN people USING (year) GROUP BY summary.year ORDER BY summary.year",
            parameters,
        )
        print("year\tsent\treceived\tpeople")
        for year, sent, received, people in rows:
            print(f"{year}\t{sent}\t{received}\t{people}")
        if top is not None and top > 0:
            heading = lambda text: f"\033[1m{text}\033[0m" if sys.stdout.isatty() else text
            print()
            print(heading("top senders"))
            for address, count in catalog.execute("SELECT email_addresses.address, COUNT(*) FROM messages JOIN email_addresses ON email_addresses.address_pk = messages.sender_address_pk" + clause + " GROUP BY email_addresses.address ORDER BY COUNT(*) DESC, email_addresses.address LIMIT ?", (*parameters, top)):
                print(f"{address}\t{count}")
            print()
            print(heading("top recipients"))
            for address, count in catalog.execute("SELECT email_addresses.address, COUNT(*) FROM recipients JOIN messages USING (message_pk) JOIN email_addresses USING (address_pk)" + clause + " GROUP BY email_addresses.address ORDER BY COUNT(*) DESC, email_addresses.address LIMIT ?", (*parameters, top)):
                print(f"{address}\t{count}")
    finally:
        catalog.close()


def report(args: argparse.Namespace) -> None:
    print_report(Path(args.archive), report_years(args.year), args.top)


def refresh_index(args: argparse.Namespace) -> None:
    archive = Path(args.archive)
    temporary = archive / "search.sqlite3.tmp"
    temporary.unlink(missing_ok=True)
    search = create_search(temporary)
    try:
        for path in archive.glob("*.mbox"):
            box = mailbox.mbox(path, factory=None, create=False)
            try:
                for key in box.iterkeys():
                    index_message(search, box.get_bytes(key, from_=False), args.index_attachments)
            finally:
                box.close()
        search.commit()
    finally:
        search.close()
    os.replace(temporary, archive / "search.sqlite3")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True, help="canonical archive directory")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest_parser = commands.add_parser("ingest")
    ingest_parser.add_argument("--owner-names-file", required=True)
    ingest_parser.add_argument("--clamav", action="store_true", required=True, help="scan new messages with on-demand ClamAV")
    ingest_parser.add_argument("--workers", type=int, default=min(os.cpu_count() or 1, 8), help="concurrent ClamAV scans (default: cores, capped at 8)")
    ingest_parser.add_argument("--index-attachments", action="store_true", help="index text attachments; non-text attachments require the planned Tika extractor")
    ingest_parser.add_argument("roots", nargs="+", metavar="ROOT")
    ingest_parser.set_defaults(function=ingest)
    review_parser = commands.add_parser("review")
    review_parser.add_argument("--run", type=int, help="only show this ingest run's observations")
    review_parser.set_defaults(function=review)
    report_parser = commands.add_parser("report")
    report_parser.add_argument("--year", help="year or inclusive year range, for example 2016 or 2010-2020")
    report_parser.add_argument("--top", type=int, default=DEFAULT_REPORT_TOP, help="top senders and recipients to show (default: 10; use 0 to suppress)")
    report_parser.set_defaults(function=report)
    refresh_parser = commands.add_parser("refresh-index")
    refresh_parser.add_argument("--index-attachments", action="store_true", help="include text attachments; non-text attachments require the planned Tika extractor")
    refresh_parser.set_defaults(function=refresh_index)
    args = parser.parse_args()
    try:
        args.function(args)
    except KeyboardInterrupt:
        print("interrupted: archive state committed through the last completed message", file=sys.stderr, flush=True)
        print_report(Path(args.archive), None, DEFAULT_REPORT_TOP)
        return 130
    except DiskFullError as error:
        print(f"disk full: {error}; archive stopped cleanly", file=sys.stderr, flush=True)
        return 1
    if args.command == "ingest":
        print_report(Path(args.archive), None, DEFAULT_REPORT_TOP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
