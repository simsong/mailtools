# mailarchiver

`mailarchiver` turns scattered email exports into a durable archive that you
can inspect with ordinary tools decades from now. It preserves the original
RFC 5322 message bytes in standard MBOX files, hashes every message for
long-term integrity, records where each message came from, and builds a local
search index that can always be discarded and rebuilt.

For each year it creates two logical archives: one for messages sent by the
archive owner and one for messages received. They begin as
`{YEAR}-Sent1.mbox` and `{YEAR}-Archive1.mbox`; additional numbered filenames
are reserved for the planned rollover support. Messages are never rewritten just
to make them easier to search: the SQLite databases and user interfaces are
derived data, while MBOX and its versioned integrity files are the durable record.

This is the initial local-ingest implementation, not yet the complete email
archiving system. It currently ingests local MBOX, EML, Maildir, and complete
Apple Mail `.emlx` messages. Gmail, IMAP, sorting/repacking, and rollover remain
planned; see [doc/implementation.md](doc/implementation.md).

## Install

Install [uv](https://docs.astral.sh/uv/) and ClamAV, configure the ClamAV
daemon and signatures, then prepare this project:

```console
cd archiver
uv sync
```

Run the project command with `uv run mailarchiver`.

Set the archive directory once for the shell session:

```console
export MAIL_ARCHIVE_DIR=/path/to/mail-archive
```

Every `mailarchiver` and `mailsearch` command below uses this value. Pass
`--archive DIRECTORY` before the command to override it for one invocation.

### Apache Tika status

Apache Tika is **not used by the program yet**. The Makefile can download and
checksum a Tika application JAR in preparation for opt-in extraction from PDF
and Office attachments, but no current ingest or search path invokes it.
Normal mail ingest and body-only search do not need Java. The current
`--index-attachments` option indexes text attachments only.

Tika requires Java 17 or newer.  The following installs the current supported
Tika application JAR into this checkout's ignored `.tools/` directory and
verifies Apache's published SHA-512 checksum; it does not install a service or
schedule any work:

```console
make install-mac
# or, on Linux:
make install-linux
```

The installer uses `TIKA_VERSION=3.3.2`.  To install a later Apache release
explicitly, set that variable after checking its release notes and checksum:

```console
make install-mac TIKA_VERSION=X.Y.Z
```

## Ingest local mail

The following command recursively reads MBOX and `.emlx` files below
`SOURCE`.  It never changes those source files.  It starts `clamd` temporarily
for the ingest run if no daemon is already listening on the configured local
socket.

### `--clamav`

`--clamav` is currently required on every ingest.  It scans each new
message through the locally configured `clamd` socket before the message is
written to a normal MBOX.  If no healthy daemon is listening, mailarchiver
starts one foreground daemon for this ingest only, reusing its loaded
signatures, and stops it afterward.  If a healthy local daemon already owns
the socket, mailarchiver uses it and leaves it running.
`MAILARCHIVER_CLAMD`, `MAILARCHIVER_CLAMDSCAN`,
`MAILARCHIVER_CLAMD_CONFIG`, and `MAILARCHIVER_CLAMD_SOCKET` override the
macOS Homebrew defaults for another local environment, including CI.

This option does **not** enable on-access scanning, a login service, or a
scheduled scan.  It requires a configured ClamAV signature database; scanner
startup or scan errors stop the current ingest rather than silently treating
mail as clean.  A positive detection is retained in `INFECTED1.mbox`.

```console
uv run mailarchiver ingest --owner-names-file owner-names.txt --clamav /path/to/source-mail
```

For example, with the project's supplied owner-token list and a new archive:

```console
MAIL_ARCHIVE_DIR="$HOME/arch-local/normalized-mail" uv run mailarchiver ingest --owner-names-file owner-names.txt --clamav "$HOME/arch-local/SLG Mail"
```

ClamAV scan workers default to the CPU count, capped at eight.  Override the
limit for a benchmark or a less capable machine with `--workers N`.

Messages are classified as `Sent` when their parsed `From:` address contains a
case-insensitive token in `owner-names.txt`; they go to the year's
`{YEAR}-Sent1.mbox` series. Other clean messages go to the year's
`{YEAR}-Archive1.mbox` series. `X-Apple-Auto-Saved` messages are logged but not
copied.

The archive directory contains:

* canonical `.mbox` files and adjacent `.mbox.integrity` files containing
  versioned `h1` complete-MBOX, `h2` raw-message, and `h3` semantic-message
  SHA-256 digests as specified in
  [doc/INTEGRITY_CONTROLS.md](doc/INTEGRITY_CONTROLS.md);
* `archive.sqlite3`, the ingest catalog and observation log; and
* `search.sqlite3`, a separately rebuildable FTS5 index.

Ingest also places `verify_mail_archive.py` in the archive. It is a small,
single-purpose Python program with no third-party dependencies. Run it to
verify every declared whole-MBOX and per-message hash without changing the archive:

```console
python3 /path/to/mail-archive/verify_mail_archive.py
```

The default index contains normalized headers and message body text only:
`text/plain` when available, otherwise rendered `text/html`.  It excludes
attachments, MIME structure, and base64 payloads. Use `--index-attachments`
to build a separate text-attachment index. PDF and Office attachment
extraction is not implemented. For a large archive, omit attachment indexing
during initial ingest and build it later with `refresh-index
--index-attachments`; the canonical mail is already safe before that derived
work begins.

One or more source roots belong at the end of `ingest`; rerunning the same
input records new observations but does not rescan or copy an already archived
message with the same normalized `Message-ID` and raw SHA-256.

After a completed or interrupted ingest, mailarchiver prints the archive
report: yearly sent/received/people totals and the 10 most frequent senders
and recipients.

During ingest, a heartbeat is written to standard error immediately, every 250
milliseconds, and when the run finishes.  It shows the elapsed
time, processed-message count, average messages per second, earliest and
latest resolved message dates, current message year, that year's count, and
the current source file with its byte-completion percentage.  On a terminal it
redraws as a five-line scoreboard; redirected output stays line-oriented for
logs.  It also counts archived mail, previously-seen duplicate skips,
autosave exclusions, and infected messages.

## Interrupts and disk space

Pressing Control-C performs a controlled shutdown: mailarchiver closes the
on-demand scanner and MBOX files, commits work through the last completed
message, refreshes integrity files, prints `interrupted: ...`, and exits with status
130 rather than a traceback.  It then prints the normal `report` output for
the committed partial archive.  If an MBOX append reports `ENOSPC`, mailarchiver
truncates that attempted append back to its prior size where possible, prints
`disk full: ...`, and exits nonzero.  Free space before continuing; do not
assume an integrity file can be refreshed when the filesystem is full.

## Review ingest observations

Every ingest receives a sequential run number and records one observation for
each source message: `archived`, `duplicate`, or `autosave-excluded`.  `review`
is the audit-log viewer; it does not reindex or refresh anything.  Without a
selector it prints all observations.  Use `--run` only to restrict the output
to one numbered ingest run:

```console
uv run mailarchiver review --run 1
```

## Report archive contents

`report` reads only `archive.sqlite3`.  It lists each year with the number of
sent and received messages and the number of distinct email addresses
appearing as a sender or recipient.  It also lists the top 10 senders and
recipients for the selected scope, excluding the archive owner's addresses.
Addresses remain in the database and in the yearly `people` count.  `--year` accepts one year or an inclusive
range; `--top N` changes the number of names (`--top 0` suppresses them).

```console
uv run mailarchiver report
uv run mailarchiver report --year 2016 --top 20
uv run mailarchiver report --year 2010-2020 --top 50
```

## Rebuild the search index

Build or rebuild the disposable index from canonical mail:

```console
uv run mailarchiver refresh-index
```

Add `--index-attachments` when text attachments should be searchable. The
rebuild keeps body/header text and attachment text in separate FTS tables so a
search client can include attachments explicitly.

## Search mail

`mailsearch` is a read-only search command.  Ordinary words search indexed
headers and body text. `to:` filters recipient addresses, `from:` filters
senders, and `subject:` filters subjects. `date:YYYY-MM-DD` selects a UTC
calendar day, while `before:` and `after:` select strictly earlier or later
mail. Supplied terms are combined with AND. The default is ten results;
`--limit 0` prints every match.  Each result starts with its stable message
number, which can be supplied alone to print the original message. Numbers
align to the widest returned value; interactive terminals render subjects in
bold, while redirected output remains plain text.

```console
uv run mailsearch to:alice@example.com budget
uv run mailsearch subject:invoice after:2024-01-01
uv run mailsearch 42
uv run mailsearch --headers 42
uv run mailsearch --html 42
uv run mailsearch --mime 42
```

Use `uv run mailsearch --help` for the complete syntax. A numbered message
normally displays the main headers and `text/plain` body; `--headers` shows
all headers, `--html` shows decoded HTML, and `--mime` shows its original MIME
source. Printing uses its catalogued MBOX location and verifies its recorded
SHA-256; it does not alter canonical message bytes.

### Graphical search on macOS

The initial graphical search tool runs on macOS using pywebview and the system
WKWebView. It has one search field with the same selectors and quoting rules as
`mailsearch`, sortable results, message and MIME-part viewing, `.eml` export
and drag-out, printing, and attachment viewing. Start it with:

```console
make gui ARGS="--archive /path/to/mail-archive"
```

Select **Search attachments** to include the separate text-attachment index in
ordinary full-text searches. Build the attachment index with `uv run
mailarchiver refresh-index --index-attachments` so that table has content.

pywebview also supports Windows and Linux, but this application is not yet
portable: attachment opening currently calls the macOS `open` command, Finder
drag-out is macOS-specific, and only the Cocoa/WKWebView bridge has been tested.
The search and SQLite service layer is portable; the desktop integration needs
small platform adapters and testing before Windows is supported.

## Test

The end-to-end tests use static MBOX and `.emlx` fixtures, including an EICAR
attachment that exercises the actual on-demand ClamAV route:

```console
make check
```
