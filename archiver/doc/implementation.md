# Mail archive normalizer implementation

## Technology decision

Implement the normalizer in Python 3.12+.  It needs reliable streaming I/O,
RFC 5322/MIME parsing, SQLite/FTS5, Gmail OAuth/API support, IMAP, and
ClamAV-process integration; Python provides all of these with the standard
library plus small, well-supported dependencies.  The observed local corpus
(about 52 GB and 1.47 million input messages) is a streaming workload.

Use the standard-library `mailbox.mbox` reader and writer.  Pass raw `bytes`,
not parsed `Message` objects, to `mbox.add()` so that MIME serialization is
never rewritten; `mailbox.mbox` handles mboxrd quoting, locking, and rewrite
recovery.  Capture the pre-append and post-flush file offsets for the future
reader.  Use the standard `email` package only for header/MIME parsing while
retaining original RFC 5322 bytes for identity hashing and output.

Use SHA-256 as the canonical hash.  A local OpenSSL 3.6.3 benchmark on this
Apple Silicon host measured 2.74 GB/s for SHA-256 on 16 KiB blocks, versus
1.61 GB/s for SHA-512 and 0.98 GB/s for SHA3-256.  Do not require BLAKE3: it
would add a dependency and is less portable for long-term verification.

## Package shape

```text
archiver/
  pyproject.toml
  src/mailarchiver/
    cli.py              ingest, verify, review, refresh-index, repack
    config.py           TOML policy and owner-names loading
    model.py            pydantic records and enums
    mbox.py             streaming reader, mboxrd encoder, verifier
    message.py          header/MIME/date/classification parsing
    catalog.py          archive.sqlite3 schema and transactions
    search.py           disposable search.sqlite3 and FTS5 rebuild
    clamav.py           clamdscan/clamscan adapter and result parsing
    ingest/
      directory.py      recursive type detection and provenance
      emlx.py           length-prefixed Apple Mail reader
      imap.py            read-only IMAP fetcher
      gmail.py           OAuth Gmail API incremental fetcher
    normalize.py        dedupe, routing, staging, publishing, sorting
    verify.py            end-to-end integrity checks
  tests/
```

Use `uv` for dependencies and every test/run target through the repository
Makefile.  Typed Pydantic structures carry all message metadata and external
API responses; dictionaries are confined to API-boundary decoding.

## Database design

`archive.sqlite3` uses WAL mode during ingest, foreign keys, explicit
transactions, and a schema version table.  Principal relations are:

```text
messages(message_pk, message_id_raw, message_id_normalized, sha256 UNIQUE,
         date_utc, date_source, category, from_address, subject, byte_length,
         clamav_status, clamav_detail, created_run)
recipients(message_pk, role, position, address, display_name)
mbox_generations(generation_pk, filename, sha256, message_count, byte_count,
                 created_run, valid)
locations(message_pk, generation_pk, byte_offset, byte_length)
sources(source_pk, kind, locator, account, folder, remote_uid)
observations(observation_pk, source_pk, source_offset, message_pk,
             disposition, run_pk, detail)
ingest_runs(run_pk, started_at, completed_at, command, version, result)
manifests(generation_pk, pathname, sha256, created_at)
```

`message_pk` is nullable in `observations` so malformed and autosave-excluded
source records are still reviewable.  The deduplication lookup is indexed on `(message_id_normalized, sha256)`;
`sha256` also supports the missing-Message-ID exception path.  Do not make
Message-ID unique.  Add indexes for date/category, sender, recipients, and
location lookup.

`search.sqlite3` has its own schema and does not use cross-database foreign
keys.  Its FTS5 table includes an unindexed `sha256` column plus searchable
headers, body text, and attachment text.  Rebuild it in a temporary database,
validate row identities against `archive.sqlite3`, then atomically replace the
old search database.

## Ingest pipeline

For every candidate source record:

1. Stream exactly the RFC 5322 bytes from its source adapter.  An `.emlx`
   adapter reads the decimal length prefix, then exactly that many bytes.
2. Hash the raw RFC 5322 bytes and parse only headers needed for identity,
   classification, and exclusion.  Resolve dates from `Date:`, then
   `Received:`, then the prior resolved message date in the same input stream.
   A singleton source file may instead derive its year from a four-digit year
   in the source path; record every fallback source in the catalog.
3. If `X-Apple-Auto-Saved` exists, commit an `autosave-excluded` observation
   and continue.  Do not write an MBOX record.
4. Look up `(normalized Message-ID, SHA-256)`.  If it exists, commit a
   `duplicate` observation and continue without antivirus or text extraction.
5. Stream the raw message to ClamAV.  A positive result routes it to
   `INFECTED`; all other nonfatal outcomes retain it in its normal category
   while recording the result.
6. Stage an mboxrd-encoded record in a same-filesystem run directory.  Record
   enough staging metadata to resume safely after interruption.
7. In one SQLite transaction, add the message, recipients, source observation,
   scanner result, and staged location.  Publish the staged MBOX changes only
   after their manifest and database state validate.

Deduplication is deliberately before ClamAV: a known archived message has
already been scanned and classified.  `--rescan` explicitly revisits stored
messages when virus definitions or policy changes.

## MBOX mechanics and sorting

Input detection must validate a stream rather than trust filename extensions.
The MBOX reader recognizes separator lines, handles mboxrd `>From ` escaping,
and reports malformed boundaries without silently merging messages.

Writers produce an envelope `From ` line plus mboxrd-escaped message bytes.
They track the byte offset and byte length of each complete record.  Output
selection enforces the 3.75 GiB limit before appending; the directory contains
no nested per-message files.

At run completion, sort each touched normal mailbox by `(resolved_date_utc,
sha256)`.  The sorter writes a new MBOX and manifest beside the original,
scans both end-to-end, compares the unordered identity sets, then atomically
updates the relevant `mbox_generations`/`locations` rows.  It retains the old
file until validation succeeds and deletes it only then.  `INFECTED` mail is
not text-extracted and is not moved into a normal mailbox.

## Antivirus and text extraction

Homebrew installed these commands:

```text
/opt/homebrew/bin/clamscan
/opt/homebrew/bin/clamdscan
/opt/homebrew/bin/freshclam
/opt/homebrew/sbin/clamd
```

`clamd` is the normal on-demand scanner: it loads the signature database once
and accepts scans through `/private/tmp/clamd.sock`; the archiver starts it
for a run when needed and stops it after the run unless an operator has
already started it.  `clamscan` remains a diagnostic fallback.  Neither an
on-access scanner, a login service, nor a scheduled scan is enabled.  Run
`freshclam` only when an operator explicitly wants new signatures.

MIME traversal and extraction are bounded by configured size, recursion,
time, and decompression limits.  Plain text and rendered HTML are indexed
first.  Attachment extractors are explicit allow-listed adapters; extraction
failures are recorded but never affect preservation.  The default policy
disables attachment extraction for infected messages.

## Remote sources

Gmail uses least-privilege OAuth where the required raw-message read scope is
available, paginates message IDs, fetches raw bytes and labels, and records
Gmail ID/thread ID/labels as provenance.  Incremental Gmail sync stores the
last successfully committed history checkpoint, with a complete-list fallback
when history has expired.

IMAP uses TLS and read-only SELECT/EXAMINE where supported.  It enumerates
folders and UIDs, fetches RFC 5322 bytes without setting `\\Seen`, and stores
UIDVALIDITY plus UID so server reset/reuse is detectable.

The `--days N` option uses `newer_than:Nd` on `messages.list`; `--after`
accepts an epoch for timezone-precise collection.  Google Takeout is an MBOX directory input.  The program does not automate
personal Takeout creation or download.

## Validation and tests

Tests use small, hand-authored MBOX and EMLX fixtures covering mboxrd quoting,
bad dates, missing IDs, same-ID/different-content messages, autosaves,
duplicate source trees, rollover, interruption recovery, and infected/
unscannable scanner outcomes.  Tests must assert message identities and bytes,
not only record counts.  Use a real local `clamd` fixture only for the
ClamAV integration test; parser and routing tests use recorded scanner result
objects rather than mock message structures.

`make check` runs unit/integration tests; `make verify ARCHIVE=...` performs
read-only archive verification.  The first acceptance run is against a copied
small subset of `SLG Mail`, followed by a full read-only inventory comparison
before any canonical archive is published.

## Delivery sequence

1. Create the package, configuration model, schema migration, MBOX/EMLX
   readers/writer, and `verify` command.
2. Implement recursive local ingest, exact dedupe, autosave exclusion,
   manifests, sorting, recovery, and ClamAV routing.
3. Add `review`, `refresh-index`, FTS5 rebuilding, and conservative body/HTML extraction.
4. Add IMAP and Gmail importers with resumable checkpoints.
5. Build the local search/view interface on the stable database and MBOX
   retrieval API.
