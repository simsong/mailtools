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
  gui/                  pywebview HTML, CSS, and JavaScript assets
  tests/
```

## Current acceptance implementation

The first implementation supports recursive local MBOX, `.eml`, Maildir, and
`.emlx` ingest, owner-token Sent classification, exact `(Message-ID, SHA-256)`
deduplication, autosave exclusion, Date/Received/path-year date fallback, a temporary on-demand `clamd`,
`INFECTED1.mbox`, SQLite catalog/FTS files, versioned `.mbox.integrity` files,
per-run observation review, and year/correspondent reports.  The top-level
`MAIL_ARCHIVE_DIR` selects the archive for every command by default; the
`--archive` option overrides it. `ingest` takes one
or more source roots as positional arguments and `--owner-names-file` selects
the reusable owner-token list.  Ingest currently requires `--clamav`: it starts
a foreground daemon only when no healthy configured socket is available, then
removes the daemon's stale socket on exit; it never enables persistent or
on-access scanning.  A thread-safe stderr scoreboard redraws in an interactive
terminal at startup, every 250 milliseconds, and completion; logs receive one-line
updates.  Its persistent phase label distinguishes `waiting for ClamAV
startup` from `checking sources` and active `ingesting`. During that wait, the
title shows startup elapsed time and the current line says that the daemon is
loading virus definitions rather than retaining stale source progress. It uses
streaming source byte offsets to show the current file and
completion percentage and reports processed source-file plus
archived/previously-seen/autosave/infected counts.  Control-C commits completed work, closes the
temporary scanner, refreshes integrity files, reports a controlled interruption, and
prints the partial-run archive report before returning 130.  An `ENOSPC` append is truncated back to the prior MBOX size where
possible and reports a controlled nonzero stop.  Acceptance coverage includes
the checked-in MBOX/EMLX corpus, source checkpoints, append resumption,
malformed metadata, publication recovery, and disposable-index failure.
Source discovery and full-file fingerprinting are interleaved with ingest.
Each changed file is archived and checkpointed before discovery continues to
the next file. A never-seen file is ingested before its complete fingerprint
is calculated; that fingerprint is still required before its checkpoint is
committed. The scanner and worker pool start lazily at the first changed file,
so an unchanged tree does not start ClamAV.
Modern Apple Mail package traversal recognizes complete
`Data/.../Messages/*.emlx` payloads and ignores MailData, plist, and detached
attachment files. It reports missing paths and macOS Full Disk Access failures
instead of treating them as empty input. `.partial.emlx` is rejected because
the cached RFC 5322 representation omits detached attachment bytes; use Apple
Mail's mailbox export to obtain a complete MBOX source.

Successful ingests also print the archive report after finalization.  The
report shows per-year totals plus the top 10 senders and recipients by default;
all sections use aligned tables with right-aligned, comma-grouped numbers, and
the correspondent tables show each address's first and last message dates.
addresses identified by a `Sent` message are filtered from correspondent lists
only, not from stored metadata or yearly people totals.  `report --top 0`
suppresses those lists.

`ingest --workers N` defaults to `min(os.cpu_count(), 8)`.  The source reader
hashes and performs duplicate admission serially; admitted messages enter a
bounded queue of at most `2N` concurrent ClamAV scans.  A single writer emits
MBOX records and SQLite rows in source order after scan completion.

Rollover, date sorting/repacking, complete recipient metadata, `verify`, richer
text extraction, IMAP, and Gmail remain planned work.  The delivered
`mailsearch` command reads both databases without writing:
it applies `to:`/`from:`/`subject:` catalog filters, UTC calendar-day
`date:`/`before:`/`after:` filters, and ANDed FTS5 terms; it prints stable
`message_pk` header lines and reads a numbered message directly from its
catalogued MBOX byte location, validating its SHA-256 before output.

The catalog has an explicit schema version and is initialized only when fresh;
unversioned or incompatible databases are rejected. `locations` and
`mbox_generations` are written as part of each message publication.

Header parsing decodes and unfolds RFC 2047 Subject values before catalog and
FTS insertion. `mailsearch` displays that catalog value directly.
Its result formatter determines number width from the returned `message_pk`
values and emits ANSI bold only for a terminal subject field.
Email-policy `compat32` header objects, including raw 8-bit `Received:`
and recipient fields, are converted to text before metadata parsing. Each
derived header field has an independent exception boundary. Broken RFC 2047
subjects retain their unfolded source text, and metadata defects are catalogued.
Sender resolution prefers a valid `From:` address, falls back to the RFC
`From:` inside a quoted nested-MBOX record and then the RFC `Sender:`
header. It recognizes Google Chat event payloads only when their Gmail thread
header and event fields are present. Chat actors are stored as
`Full Name (Google Chat)` so they cannot be mistaken for email addresses.
Reports render the remaining empty sender identity as `(missing sender)`.
Parsed dates outside 1900 through the next calendar year are rejected before
the normal Received/previous-message/path fallbacks.

Numbered-message display parses the verified raw bytes with the standard
library email parser. It renders the principal headers and prefers
non-attachment `text/plain` parts; it uses Beautiful Soup when only HTML is
available. XML-looking XHTML declared as `text/html` uses the forgiving HTML
parser while locally suppressing only Beautiful Soup's XML-as-HTML warning.
`--headers`, `--html`, and `--mime` select full headers, decoded
HTML parts, and exact original MIME source respectively.

The `gui/` prototype uses pywebview's Cocoa/WKWebView backend on macOS.  Its
Python API delegates query parsing, SQLite reads, and direct MBOX retrieval to
the same typed functions used by `mailsearch`.  Search pages request 101 rows
to return 100 plus a `has_more` indicator.  The UI is conventional: a search
toolbar above a result list and message pane. Independent message windows load
the same static application with a message-number parameter.

Result ordering is a server-side SQL whitelist over date, case-folded subject,
or case-folded sender with a stable message-number tie break. The listbox owns
keyboard focus after a pointer selection and implements Up/Down selection.
Result paperclips use attachment counts joined from the disposable search
metadata without rereading MBOX content. Each row reserves a third line; after
the header rows are painted, JavaScript queues one page of preview IDs through
the Python bridge. A single-worker executor reads the indexed 18-word previews,
and JavaScript polls the typed result batch until it can fill the rows. Global macOS Command-key handlers
select numeric MIME part IDs or raw source.
The toolbar's **Search attachments** checkbox passes an explicit boolean to the
typed search service. Ordinary terms search `message_fts` by default; when the
box is selected they search the union of `message_fts` and `attachment_fts`.
Metadata selectors are unchanged.

MIME descriptions and API responses are Pydantic models.  Body content is
loaded only for the selected part.  HTML parsing removes active elements,
event handlers, file URLs, and unsafe URL schemes, replaces image CID references
with message-local data, and injects a restrictive CSP.  The HTML is displayed
inside a sandboxed iframe. Remote image URLs are omitted unless the user
explicitly enables them for that view. Individual image and PDF attachments
are base64-transferred only on an explicit preview action; other attachment
payloads are written to a private temporary directory before macOS opens them.

`search.sqlite3` contains separate `message_fts` and `attachment_fts` virtual
tables so message text remains searchable without attachment matches.
`message_metadata`, keyed by message SHA-256, contains an
attachment count and deterministic 18-word body preview, and
`message_attachments`, keyed by SHA-256 and attachment
ordinal with the MIME-walk part ID, decoded filename, and normalized MIME type.
Indexing parses each message once for FTS body text and attachment metadata;
`--index-attachments` additionally writes decoded text attachments to
`attachment_fts`.
The tables are derived and are replaced together with FTS by `refresh-index`.

`.eml` export writes the bytes returned by hash-verified direct retrieval.
Finder dragging uses a temporary `.eml` file URL and the Cocoa webview's native
file/link drag support. Only the message-file icon well is draggable; the
header region remains normal selectable text. `window.print()` is handled by pywebview's WKWebView
print operation. Temporary exports live only for the application process.

The shell page permits `unsafe-eval` only for local scripts because pywebview
constructs its typed Python API wrappers with JavaScript `Function`. Message
HTML remains isolated in a sandboxed frame with its own restrictive CSP. The
`gui-smoke` Makefile target verifies that Cocoa injects the bridge and that
JavaScript can call the Python `status()` API.

`aisummarize.py` implements the `summarize` console entry point. It reads stdin
before doing any native work and invokes a content-addressed Swift helper built
into `~/Library/Caches/mailarchiver` from the packaged `apple_summary.swift`
source. The helper uses `SystemLanguageModel.default`, checks model
availability, and asks for one faithful abstractive sentence of at most 30 words while
treating input text as untrusted content rather than instructions. Neither the
input nor output is canonical archive data.

Use `uv` for dependencies and every test/run target through the repository
Makefile.  Typed Pydantic structures carry all message metadata and external
API responses; dictionaries are confined to API-boundary decoding.

`standalone_verify.py` is itself limited to the Python standard library. At
ingest startup it copies its own source atomically to
`verify_mail_archive.py` in the archive. The installed script accepts only the
hybrid format in [INTEGRITY_CONTROLS.md](INTEGRITY_CONTROLS.md). It streams and
validates the JSON declarations, complete-MBOX `h1` hashes, recovered-message
`h2` hashes, and semantic-message `h3` hashes, returning nonzero on missing,
orphaned, malformed, unsupported, or mismatched files. It neither imports the
package nor reads SQLite.

`write_integrity_files()` streams catalog locations in MBOX byte order and
uses each catalogued raw SHA-256 to resolve mboxrd `>From ` ambiguity. It then
atomically writes deterministic JSON control records followed by the TSV table.
The initial declarations are `h1` (complete MBOX, SHA-256), `h2` (recovered
RFC 5322 bytes, SHA-256), and `h3` (semantic-message version 1, SHA-256).
Semantic version 1 applies DKIM relaxed header and simple body canonicalization
to the selected stable/delivery headers documented in `INTEGRITY_CONTROLS.md`;
it includes `Delivered-To` and excludes mutable `Status` and `X-Status` fields.

## Database design

`archive.sqlite3` uses WAL mode during ingest, foreign keys, explicit
transactions, and a schema version table.  Principal relations are:

```text
email_addresses(address_pk, address UNIQUE)
messages(message_pk, message_id_normalized, sha256, sender_address_pk, subject,
         date_utc, date_source, category,
         UNIQUE(message_id_normalized, sha256))
recipients(message_pk, address_pk)
mbox_generations(generation_pk, filename, sha256, message_count, byte_count)
locations(message_pk, generation_pk, byte_offset, byte_length)
source_files(source_path, modified_at_ns, byte_length, sha256, checked_at,
             completed_run)
observations(observation_pk, source_path, source_offset, source_sha256,
             message_pk, disposition, run_pk, detail)
metadata_defects(message_pk, field, detail)
ingest_runs(run_pk, started_at, completed_at, result, detail)
```

`message_pk` is nullable in `observations` so malformed and autosave-excluded
source records are still reviewable.  The deduplication lookup is indexed on `(message_id_normalized, sha256)`;
`sha256` also supports the missing-Message-ID exception path.  Do not make
Message-ID unique.  `email_addresses.address`, `messages.sender_address_pk`,
and `recipients.address_pk` are indexed; recipient role and ordering are not
preserved.  Add indexes for date/category and
location lookup.

`search.sqlite3` has its own schema and does not use cross-database foreign
keys. Its main FTS5 table includes an unindexed `sha256` column plus searchable
headers and selected body text: `text/plain` first, otherwise rendered
`text/html`, otherwise a safe single-part fallback. A second FTS5 table stores
text-attachment content only when requested, allowing the GUI to include it
without changing default body-search semantics. Binary attachment bytes are
excluded. The Makefile's `install-mac` and `install-linux` targets
download Apache Tika's checksum-verified application JAR to the ignored
project-local `.tools/tika/<version>/` directory; Tika remains an optional
future extractor for PDF and Office attachments, not a service.  Rebuild the
index in a temporary database,
validate row identities against `archive.sqlite3`, then atomically replace the
old search database. Live indexing and `refresh-index` both exclude
`INFECTED` and the reserved `MALFORMED` quarantine category; rebuild recognizes
numbered quarantine MBOX filenames.
Ordinary `mailsearch` listings and reports select only `Sent` and `Archive`;
the authoritative catalog still retains every quarantine record.
Normal ingest publishes canonical MBOX/catalog state first, then attempts the
disposable FTS insertion for normal Sent and Archive mail. Extraction or indexing failure records a
`search-index` metadata defect without rolling back canonical mail.

## Ingest pipeline

For every candidate source record:

1. Discover one physical source file, then fully process and checkpoint it
   before discovering the next. For a never-seen file, ingest messages before
   calculating the complete source SHA-256. For a known file, fingerprint
   first to skip a complete match; for a grown MBOX, compare the old-length
   prefix and resume only at a validated appended-message boundary. Drain
   queued scans, calculate any deferred fingerprint, and publish the updated
   file checkpoint at every file boundary.
2. Stream exactly the RFC 5322 bytes from its source adapter.  An `.emlx`
   adapter reads the decimal length prefix, then exactly that many bytes.
3. Hash the raw RFC 5322 bytes and parse only headers needed for identity,
   classification, and exclusion.  Resolve dates from `Date:`, then
   `Received:`, then the prior resolved message date in the same input stream.
   A singleton source file may instead derive its year from a four-digit year
   in the source path; record every fallback source in the catalog.
   An unexpected parser exception records the source path, byte offset, raw
   hash, and exception before stopping; already queued earlier messages are
   drained and committed first.
4. If `X-Apple-Auto-Saved` exists, commit an `autosave-excluded` observation
   and continue.  Do not write an MBOX record.
5. Look up `(normalized Message-ID, SHA-256)`.  If it exists, commit a
   `duplicate` observation and continue without antivirus or text extraction.
6. Stream the raw message to ClamAV.  A positive result routes it to
   `INFECTED`; all other nonfatal outcomes retain it in its normal category
   while recording the result.
7. Durably journal the target MBOX, its prior size/existence, and the message
   identity, then append and flush the mboxrd-encoded raw bytes.
8. Keep message, recipient, defect, observation, and location rows in one
   catalog transaction until the append succeeds. Commit the authoritative
   catalog and clear the journal. An exception or the next ingest startup
   truncates an uncatalogued append and refreshes integrity files; a catalogued append
   is validated and retained. Index disposable search content afterward only
   for normal Sent and Archive mail.

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
For an original zero-byte message, standard MBOX contributes one payload
separator newline. Direct retrieval maps exactly that one-byte representation
back to empty bytes only when the catalogued SHA-256 is the empty-byte digest.
The standard-library writer's `>From ` representation is ambiguous when the
source already contained a literal `>From ` line. The reader enumerates a
bounded set of quote interpretations and selects only the candidate matching
the authoritative raw-message SHA-256; unresolved high-ambiguity input fails
closed.

At run completion, sort each touched normal mailbox by `(resolved_date_utc,
sha256)`.  The sorter writes a new MBOX and integrity file beside the original,
scans both end-to-end, compares the unordered identity sets, then atomically
updates the relevant `mbox_generations`/`locations` rows.  It retains the old
file until validation succeeds and deletes it only then.  `INFECTED` and
`MALFORMED` quarantine mail is not FTS-extracted and is not moved into a normal
mailbox.

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
`MAILARCHIVER_CLAMD`, `MAILARCHIVER_CLAMDSCAN`, `MAILARCHIVER_CLAMD_CONFIG`,
and `MAILARCHIVER_CLAMD_SOCKET` override the macOS Homebrew defaults for a
separately configured local environment such as CI.

MIME traversal and extraction are bounded by configured size, recursion,
time, and decompression limits.  Plain text and rendered HTML are indexed
first for normal mail. Attachment extractors are explicit allow-listed
adapters; extraction failures are recorded but never affect preservation.
Quarantine categories are omitted from FTS entirely.

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

1. Create the package, configuration model, versioned fresh schema, MBOX/EMLX
   readers/writer, and `verify` command.
2. Implement recursive local ingest, exact dedupe, autosave exclusion,
   integrity files, sorting, recovery, and ClamAV routing.
3. Add `review`, `refresh-index`, FTS5 rebuilding, and conservative body/HTML extraction.
4. Add IMAP and Gmail importers with resumable checkpoints.
5. Build the local search/view interface on the stable database and MBOX
   retrieval API.
