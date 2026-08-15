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

## Ingest local mail

The following command recursively reads MBOX and `.emlx` files below
`SOURCE`.  It never changes those source files.  It starts `clamd` temporarily
for the ingest run if no daemon is already listening on the configured local
socket.

```console
uv run mailarchiver --archive /path/to/mail-archive ingest --owner-names-file owner-names.txt --clamav on-demand /path/to/source-mail
```

For example, with the project's supplied owner-token list and a new archive:

```console
uv run mailarchiver --archive "$HOME/arch-local/normalized-mail" ingest --owner-names-file owner-names.txt --clamav on-demand "$HOME/arch-local/SLG Mail"
```

Messages are classified as `Sent` when their parsed `From:` address contains a
case-insensitive token in `owner-names.txt`; other clean messages go to
`{YEAR}-Archive1.mbox`.  A positive ClamAV detection goes to
`INFECTED1.mbox`.  `X-Apple-Auto-Saved` messages are logged but not copied.

The archive directory contains:

* canonical `.mbox` files and adjacent SHA-256 files;
* `archive.sqlite3`, the ingest catalog and observation log; and
* `search.sqlite3`, a separately rebuildable FTS5 index.

One or more source roots belong at the end of `ingest`; rerunning the same
input records new observations but does not rescan or copy an already archived
message with the same normalized `Message-ID` and raw SHA-256.

## Review ingest observations

Every ingest receives a sequential run number and records one observation for
each source message: `archived`, `duplicate`, or `autosave-excluded`.  `review`
is the audit-log viewer; it does not reindex or refresh anything.  Without a
selector it prints all observations.  Use `--run` only to restrict the output
to one numbered ingest run:

```console
uv run mailarchiver --archive /path/to/mail-archive review --run 1
```

## Report archive contents

`report` reads only `archive.sqlite3`.  By default it lists each year with the
number of sent and received messages and the number of distinct email
addresses appearing as a sender or recipient.  `--year` accepts one year or
an inclusive range.  `--top N` additionally lists the top N senders and
recipients and requires `--year`.

```console
uv run mailarchiver --archive /path/to/mail-archive report
uv run mailarchiver --archive /path/to/mail-archive report --year 2016 --top 20
uv run mailarchiver --archive /path/to/mail-archive report --year 2010-2020 --top 50
```

## Test

The end-to-end tests use static MBOX and `.emlx` fixtures, including an EICAR
attachment that exercises the actual on-demand ClamAV route:

```console
make check
```
