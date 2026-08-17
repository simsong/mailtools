# mailarchiver

`mailarchiver` is a local, byte-preserving normalizer for a personal mail
archive.  Its current acceptance implementation ingests MBOX and Apple Mail
`.emlx` files from a directory tree, stores each accepted message in a
canonical MBOX, records provenance in SQLite, and creates a disposable FTS5
search database.

This is the initial local-ingest implementation, not yet the complete
ten-year archive system.  Gmail, IMAP, sorting/repacking, rollover, and
verification are planned; see [doc/implementation.md](doc/implementation.md).

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

### Optional Apache Tika

Apache Tika will be used for opt-in extraction from binary attachments such as
PDF and Office files.  It is not a daemon and is not needed for normal mail
ingest or body-only search.  The current `--index-attachments` option indexes
text attachments; binary attachment extraction will be added in a later
change.

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
case-insensitive token in `owner-names.txt`; other clean messages go to
`{YEAR}-Archive1.mbox`.  `X-Apple-Auto-Saved` messages are logged but not
copied.

The archive directory contains:

* canonical `.mbox` files and adjacent SHA-256 files;
* `archive.sqlite3`, the ingest catalog and observation log; and
* `search.sqlite3`, a separately rebuildable FTS5 index.

The default index contains normalized headers and message body text only:
`text/plain` when available, otherwise rendered `text/html`.  It excludes
attachments, MIME structure, and base64 payloads.  Use `--index-attachments`
to include text attachments.  PDF and Office attachment extraction is planned
through an optional Apache Tika installation.

One or more source roots belong at the end of `ingest`; rerunning the same
input records new observations but does not rescan or copy an already archived
message with the same normalized `Message-ID` and raw SHA-256.

After a completed or interrupted ingest, mailarchiver prints the archive
report: yearly sent/received/people totals and the 10 most frequent senders
and recipients.

During ingest, a heartbeat is written to standard error immediately, every two
seconds, and when the run finishes.  It shows the ingest start time, elapsed
time, processed-message count, average messages per second, earliest and
latest resolved message dates, current message year, that year's count, and
the current source file with its byte-completion percentage.  On a terminal it
redraws as a five-line scoreboard; redirected output stays line-oriented for
logs.  It also counts archived mail, previously-seen duplicate skips,
autosave exclusions, and infected messages.

## Interrupts and disk space

Pressing Control-C performs a controlled shutdown: mailarchiver closes the
on-demand scanner and MBOX files, commits work through the last completed
message, refreshes manifests, prints `interrupted: ...`, and exits with status
130 rather than a traceback.  It then prints the normal `report` output for
the committed partial archive.  If an MBOX append reports `ENOSPC`, mailarchiver
truncates that attempted append back to its prior size where possible, prints
`disk full: ...`, and exits nonzero.  Free space before continuing; do not
assume a manifest can be refreshed when the filesystem is full.

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

After upgrading from the earlier raw-MIME index, rebuild the disposable index:

```console
uv run mailarchiver refresh-index
```

Add `--index-attachments` only when text attachments should be searchable.

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
```

Use `uv run mailsearch --help` for the complete syntax.  Printing a message
currently scans canonical MBOX files by its recorded SHA-256; it does not alter
the archive.

## Test

The end-to-end tests use static MBOX and `.emlx` fixtures, including an EICAR
attachment that exercises the actual on-demand ClamAV route:

```console
make check
```
