# Mail archive normalizer requirements

## Purpose

Create and maintain a cleartext, personal, long-lived archive of all of
user email.  The archive is canonical; all databases and user
interfaces are derived from it and may be recreated.

The system must ingest the existing local archive, Gmail, IMAP accounts, and
Apple Mail message files.  It must be safe to rerun an ingest operation on
the same source without duplicating or rescanning messages already archived.

## Canonical archive layout

All deliverables reside in one archive directory.

* Mail is stored only in standard MBOX files, using byte-preserving mboxrd
  quoting.  Do not retain a per-message EML corpus.
* Normal mail is partitioned by resolved message year and category:
  `{YEAR}-Sent1.mbox` and `{YEAR}-Archive1.mbox`.
* A file rolls over before it reaches 3.75 GiB.  Later parts are named
  `{YEAR}-Sent2.mbox`, `{YEAR}-Sent3.mbox`, `{YEAR}-Archive2.mbox`, etc.
* Messages detected as infected are instead placed in `INFECTED.mbox`, with
  the same numeric rollover rule if needed.  They are never discarded or
  altered.
* A message's category is **Sent** if the parsed `From:` address contains,
  case-insensitively, one of names in owner-names.txt; otherwise it is **Archive**.  The aliases are
  configurable, and the matched address is retained.
* The date is the valid RFC 5322 `Date:` value; otherwise use the earliest
  valid `Received:` timestamp.  A message lacking both inherits the prior
  resolved date in the same input mailbox stream.  If it is the only message
  in that file and the only file in its containing directory, derive the year
  from a four-digit year in the source path and record that fallback.  Never
  route ordinary input to a `0000` mailbox merely because its date is absent.
* `X-Apple-Auto-Saved` messages are excluded entirely.  Their source and
  exclusion reason are retained in the primary database, but no MBOX copy is
  created.
* Each finished MBOX has a SHA-256 manifest recording its byte hash, message
  count, and ordered `(Message-ID, message SHA-256)` records.

The archive lives on the encrypted laptop filesystem.  BorgBackup and
Backblaze provide independent backup; archive-internal encryption is not a
requirement.

## Deduplication and provenance

* A duplicate is only a message with both the same normalized `Message-ID`
  and the same SHA-256 of its RFC 5322 message bytes.  Never collapse all
  messages sharing only a Message-ID.
* Messages missing Message-ID are retained and identified by their SHA-256;
  they are reported as metadata exceptions.
* The archive records every source observation: source kind, source path or
  remote account/folder/UID, source byte offset where applicable, ingest run,
  and disposition (`archived`, `duplicate`, `autosave-excluded`, or error).
* Idempotence is at message level.  After a raw message hash and Message-ID
  have been obtained, a matching stored identity is skipped before ClamAV,
  text extraction, and MBOX writing.  A deliberate rescan/reindex mode is
  separate from normal ingest.

## Malware handling

* Each new message is streamed to ClamAV before normal archiving.
* The local CLI currently requires the `--clamav` switch.  This starts one
  foreground `clamd` for the ingest when the configured local socket is not
  healthy, reuses a healthy existing daemon without stopping it, and never
  enables on-access or scheduled scanning.
* `ingest --workers N` controls the bounded ClamAV scan pool.  Its default is
  the detected CPU count capped at eight.  Source reading, duplicate decisions,
  SQLite commits, and canonical MBOX publication remain single-writer.
* Ingest progress is written to standard error at startup, every two seconds,
  and completion.  An interactive terminal receives a redraw-in-place
  scoreboard; redirected output remains line-oriented.  Both report the run
  start, elapsed time, processed count, average rate, resolved date range,
  current year/current-year count, current source file, and source-file byte
  completion percentage.  It separately reports archived, duplicate
  (previously-seen and skipped), autosave-excluded, and infected counts.
* Control-C is a graceful stop: close scanner and MBOX resources, commit
  completed messages and observations, refresh manifests, report interruption,
  print the standard archive report for the completed partial run, and return
  exit status 130 without a traceback.  An `ENOSPC` MBOX append
  must be rolled back to the prior file size where possible, reported, and
  stopped without silently treating the message as archived.
* Completed and interrupted ingests print the archive report.  Reports always
  include year totals and default to the top 10 senders and recipients for the
  selected scope.  Addresses identified by Sent classification are suppressed
  from these correspondent lists only; they remain in the catalog and yearly
  people counts.  `--top 0` suppresses correspondent lists.
* ClamAV outcomes are `clean`, `infected`, `unscannable`, or `scanner-error`,
  with scanner version, signature database version, and diagnostic retained.
* Only a positive detection routes a message to `INFECTED.mbox`; an
  unscannable attachment or scanner failure does not destroy or silently
  exclude a message.
* Infected mail remains searchable by headers and body text, but attachment
  text extraction is disabled by default.

## Primary metadata database

`archive.sqlite3` is authoritative metadata, not the authoritative message
content.  It tracks at least:

* logical message identity: raw and normalized Message-ID, message SHA-256,
  date and date source, category, byte length, ClamAV result;
* parsed sender and recipient address foreign keys, and decoded/unfolded
  Subject headers; malformed header encoding falls back safely without
  affecting preservation;
* each final MBOX filename, message byte offset, byte length, and archive
  generation; and
* sources, ingest runs, exclusions, duplicates, validation results, and
  manifests.

Logical messages and physical locations are separate relations.  MBOX offsets
are generation-specific and must be replaced atomically when a file is
sorted or repacked.

Email address text is normalized into `email_addresses(address_pk, address)`.
`messages.sender_address_pk` and `recipients.address_pk` reference that table;
recipient role and header order are intentionally not retained.

## Search database

`search.sqlite3` is a separate, disposable SQLite FTS5 database.  It indexes
message SHA-256, normalized headers, `text/plain` body text when present,
otherwise rendered `text/html`, otherwise safe single-part message text.  It
does not index attachment bytes by default.  `--index-attachments` enables
text attachment indexing.  Binary attachment extraction is a separately
configured, opt-in capability using Apache Tika; the Tika JAR is installed
locally and checksum-verified, never run as a service.  It must be fully rebuildable from the
canonical MBOX files and `archive.sqlite3`, and is not backed up as a required
preservation object.

`mailsearch` is a read-only command-line consumer of both databases.  It
accepts ordinary full-text terms plus `to:ADDRESS` recipient, `from:ADDRESS`
sender, `subject:TEXT`, `date:YYYY-MM-DD`, `before:YYYY-MM-DD`, and
`after:YYYY-MM-DD` filters, intersecting every supplied term. `date:` selects
the specified UTC calendar day; `before:` and `after:` exclude the specified
day. Results default to ten
one-line headers, prefixed by the stable `messages.message_pk`; `--limit 0`
prints all matches.  Supplying one such number prints the original RFC 5322
message bytes from canonical MBOX storage.  The current implementation finds
that message through a catalogued generation-specific MBOX location and
verifies the recovered bytes against its SHA-256 before printing. New ingests
record locations; `refresh-locations` rebuilds them from existing canonical
MBOX files without modifying message bytes.
It decodes/unfolds historical RFC 2047 subject values while printing, so an
older catalog remains readable without rewriting canonical MBOX files.
`refresh-subjects` rewrites older `messages.subject` values from canonical
MBOX data so the catalog itself retains decoded, human-readable subjects.
Run `refresh-index` afterward to normalize historical FTS header content too.
Within one result set, message numbers are right-aligned to that set's widest
number. Interactive terminals render subjects in ANSI bold; redirected output
contains no terminal control codes.

For a numbered message, the default display shows `To`, `From`, `Cc`,
`Subject`, and `Date` headers plus all non-attachment `text/plain` parts. If
no plain-text part exists, it renders non-attachment `text/html` parts to
plain text with Beautiful Soup. `--headers` includes every header; `--html`
prints decoded HTML parts; `--mime` prints the original RFC 5322/MIME source,
including all MIME parts and attachment encodings.

All archive commands use `MAIL_ARCHIVE_DIR` as their default archive directory.
`--archive DIRECTORY` overrides that environment variable. If neither is set,
the command fails before reading or writing an archive.

## Ingest sources

* Recursive local-directory ingest recognizes MBOX streams, Apple Mail MBOX
  packages, Maildir, individual RFC 5322 files, and Apple `.emlx` files.
* `.emlx` input uses its leading decimal byte count to select exactly the
  RFC 5322 message; Apple's trailing plist metadata is not part of the
  message hash or output.
* Gmail ingest uses OAuth and the Gmail API for incremental acquisition of
  raw messages and labels.  It supports a rolling `--days N` mode using
  Gmail's `newer_than:Nd` query.  Google Takeout MBOX is supported as an offline,
  one-time baseline input; personal Takeout is not assumed to be
  programmatically triggerable.
* IMAP ingest supports TLS and authenticated account configuration, records
  account/folder/UID provenance, and retrieves RFC 5322 bytes without marking
  messages read or modifying the remote mailbox.

## Sorting, validation, and recovery

* At the end of an ingest run, touched normal MBOX files are sorted by
  resolved timestamp and then message SHA-256 for deterministic ties.
* Sorting writes a same-directory temporary replacement and preserves the
  prior file as a backup.
* The replacement and backup are parsed end-to-end.  Their unordered sets of
  `(Message-ID, SHA-256)` must match exactly before the backup is deleted.
* The MBOX byte hash, manifests, locations, and metadata database updates are
  published transactionally.  Interrupted runs leave either the old verified
  archive or a recoverable temporary/backup pair; they never publish a partial
  archive as valid.
* A `verify` command is strictly read-only: it reparses every canonical MBOX,
  checks manifests, offsets, and database rows, and reports duplicate-policy
  violations.
* `refresh-index` rebuilds the disposable FTS database. `refresh-subjects`
  rebuilds decoded catalog subjects from canonical MBOX files. `refresh-locations`
  rebuilds catalogued MBOX offsets from canonical MBOX files. `review` queries the
  committed source-observation log by run, source, and disposition.

## Scope boundaries

The first release is a local command-line normalizer and verifier.  Its TOML
configuration holds archive and scanner policy; `owner-names.txt` remains a
separate, one-name-per-line reusable classification input.  A local
special-purpose search and message-viewing interface is a consumer of
the two SQLite databases, not a reason to depend on Thunderbird or FoxTrot.
No source mailbox is modified by this program.
