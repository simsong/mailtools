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
* Messages detected as infected are instead placed in `INFECTED1.mbox`, with
  the same numeric rollover rule if needed.  They are never discarded or
  altered.
* A message's category is **Sent** if the parsed `From:` address contains,
  case-insensitively, one of names in owner-names.txt; otherwise it is **Archive**.  The aliases are
  configurable, and the matched address is retained.
* The date is the valid RFC 5322 `Date:` value; otherwise use the earliest
  valid `Received:` timestamp.  Years before 1900 or more than one year in the
  future are implausible and invalid.  A message lacking both inherits the prior
  resolved date in the same input mailbox stream.  If it is the only message
  in that file and the only file in its containing directory, derive the year
  from a four-digit year in the source path and record that fallback.  Never
  route ordinary input to a `0000` mailbox merely because its date is absent.
* `X-Apple-Auto-Saved` messages are excluded entirely.  Their source and
  exclusion reason are retained in the primary database, but no MBOX copy is
  created.
* Each finished MBOX has an adjacent `.mbox.integrity` file in the versioned
  hybrid format specified by [INTEGRITY_CONTROLS.md](INTEGRITY_CONTROLS.md).
  Its JSON control records declare `h1` as SHA-256 over the complete MBOX,
  `h2` as SHA-256 over each recovered original RFC 5322 message, and `h3` as
  SHA-256 over semantic-message standard version 1. Its TSV region records
  ordered message identifiers and tagged `h2:` and `h3:` digests.
* A zero-byte source message retains the SHA-256 identity of empty bytes. Direct
  retrieval removes only the single separator newline necessarily introduced
  by standard MBOX encoding, and only when that exact empty digest is expected.
* Because the standard-library MBOX writer does not distinguish an escaped
  source `From ` line from an original literal `>From ` line, direct retrieval
  considers the bounded possible interpretations and accepts only the one whose
  SHA-256 matches the catalogued original bytes.

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
  raw message SHA-256, and disposition (`archived`, `duplicate`,
  `autosave-excluded`, or error). Parser failures retain the exception detail
  and identify the source record without printing message content.
* Idempotence is at message level.  After a raw message hash and Message-ID
  have been obtained, a matching stored identity is skipped before ClamAV,
  text extraction, and MBOX writing.  A deliberate rescan/reindex mode is
  separate from normal ingest.
* Every recognized local source file records its absolute path, nanosecond
  modification time, byte length, complete-file SHA-256, last check time, and
  completing ingest run.  Reingest always verifies content: a matching full
  SHA-256 skips the file without parsing its messages.  If a file grew, ingest
  first compares the SHA-256 of the old length.  A matching MBOX prefix followed
  by a valid `From ` boundary resumes at that byte offset; all other changes
  reprocess the whole file.  The checkpoint is updated only after the selected
  region and its queued scans finish and the source metadata remains stable.
  Discovery, ingest, fingerprinting, and checkpointing proceed one file at a
  time; ingest must not pre-hash the complete source tree or a never-seen first
  file before archiving its messages. A new file's complete fingerprint is
  calculated before its checkpoint is committed. A later source failure or
  interruption retains every earlier fully published file.

## Malware handling

* Each new message is streamed to ClamAV before normal archiving.
* The local CLI currently requires the `--clamav` switch.  This starts one
  foreground `clamd` for the ingest when the configured local socket is not
  healthy, reuses a healthy existing daemon without stopping it, and never
  enables on-access or scheduled scanning.
* `ingest --workers N` controls the bounded ClamAV scan pool.  Its default is
  the detected CPU count capped at eight.  Source reading, duplicate decisions,
  SQLite commits, and canonical MBOX publication remain single-writer.
* Ingest progress is written to standard error at startup, every 250
  milliseconds, and completion.  An interactive terminal receives a
  redraw-in-place scoreboard; redirected output remains line-oriented.  Both report the phase,
  including `checking sources`, `waiting for ClamAV startup`, and `ingesting`, plus elapsed
  time, processed message and completed source-file counts, average message rate, resolved date range,
  current year/current-year count, current source file, and source-file byte
  completion percentage.  It separately reports archived, duplicate
  (previously-seen and skipped), autosave-excluded, and infected counts.
  While ClamAV loads virus definitions, every refresh explicitly identifies
  that wait and shows its increasing startup elapsed time instead of a stale
  source-file status.
* Control-C is a graceful stop: close scanner and MBOX resources, commit
  completed messages and observations, refresh integrity files, report interruption,
  print the standard archive report for the completed partial run, and return
  exit status 130 without a traceback.  An `ENOSPC` MBOX append
  must be rolled back to the prior file size where possible, reported, and
  stopped without silently treating the message as archived.
* Every ingest run records its completion time, result, and failure detail.
  An unexpected parser failure drains earlier queued messages, closes
  resources, refreshes integrity files for committed MBOX changes, and leaves a
  rerunnable error observation containing the source offset and raw SHA-256.
* Before each MBOX append, ingest durably records the target, prior length,
  message identity, and whether the target already existed. Catalog changes
  remain uncommitted until the append is complete. On an exception or the next
  startup after process death, an uncatalogued append is removed; a catalogued
  append is hash-validated, retained, and its journal is cleared.
* Completed and interrupted ingests print the archive report.  Reports always
  include year totals and default to the top 10 senders and recipients for the
  selected scope.  All report sections are aligned tables with right-aligned,
  comma-grouped numeric columns. Correspondent tables include the first and
  last message dates for each address. Addresses identified by Sent classification are suppressed
  from these correspondent lists only; they remain in the catalog and yearly
  people counts.  `--top 0` suppresses correspondent lists.
* ClamAV outcomes are `clean`, `infected`, `unscannable`, or `scanner-error`,
  with scanner version, signature database version, and diagnostic retained.
* Only a positive detection routes a message to `INFECTED1.mbox`; an
  unscannable attachment or scanner failure does not destroy or silently
  exclude a message.
* Infected and malformed quarantine mail remains catalogued but is excluded
  from the disposable search index, ordinary search listings, reports, and
  correspondent statistics. Its canonical MBOX content remains available for
  an explicit future quarantine-review workflow.

## Primary metadata database

`archive.sqlite3` is authoritative metadata, not the authoritative message
content.  It tracks at least:

* logical message identity: raw and normalized Message-ID, message SHA-256,
  date and date source, category, byte length, ClamAV result;
* parsed sender and recipient identity foreign keys, and decoded/unfolded
  Subject headers; sender identity uses a valid `From:` address, then a valid
  `From:` inside a quoted nested-MBOX record, then a valid RFC `Sender:`
  address. A narrowly recognized Google Chat event with none of these
  uses its embedded full name suffixed by `(Google Chat)`; all other missing
  senders remain empty in metadata and display as `(missing sender)` in reports.
  Every parser-provided header value is normalized to text,
  malformed fields fall back independently without affecting preservation,
  and their exception types and diagnostics are recorded;
* each final MBOX filename, message byte offset, byte length, and archive
  generation; and
* sources, ingest runs, exclusions, duplicates, validation results, and
  integrity metadata.

Logical messages and physical locations are separate relations.  MBOX offsets
are generation-specific and must be replaced atomically when a file is
sorted or repacked.

Email address text is normalized into `email_addresses(address_pk, address)`.
`messages.sender_address_pk` and `recipients.address_pk` reference that table;
recipient role and header order are intentionally not retained. The address
table also stores explicitly labeled non-email Google Chat identities.

## Search database

`search.sqlite3` is a separate, disposable SQLite FTS5 database.  It indexes
normal Sent and Archive message SHA-256, normalized headers, `text/plain` body text when present,
otherwise rendered `text/html`, otherwise safe single-part message text.  It
parses XML-looking content declared as `text/html` with the same forgiving HTML
rules without emitting parser diagnostics. Body/header text and attachment
text occupy separate FTS5 tables so callers can exclude attachments from the
default search. It does not index attachment bytes by default.
`--index-attachments` populates the separate table with decoded text
attachments. Binary attachment extraction through Apache Tika is not yet
implemented; the optional Tika installer only downloads and verifies the JAR.
The search database must be fully rebuildable from the
canonical MBOX files and `archive.sqlite3`, and is not backed up as a required
preservation object.
It excludes `INFECTED` and `MALFORMED` quarantine categories even when
attachment indexing is requested. `refresh-index` applies the same exclusion
when rebuilding from canonical MBOX files.
For every indexed message, the disposable database records an attachment count
and one ordered metadata row per MIME attachment containing its MIME-walk part
ID, decoded filename, and normalized MIME type. This metadata is derived during
the same MIME parse as body indexing and is rebuilt by `refresh-index`; it does
not make attachment payload bytes canonical database content.
The message metadata also stores a deterministic, whitespace-collapsed preview
of the first 18 words of the preferred non-attachment body. An ellipsis marks a
truncated body.
Index extraction and insertion happen after canonical MBOX/catalog publication.
An indexing failure is recorded as a metadata defect and does not reject mail;
`refresh-index` repairs missing disposable content.

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
verifies the recovered bytes against its SHA-256 before printing. Every ingest
records the location as part of the same publication as the message catalog row.
Within one result set, message numbers are right-aligned to that set's widest
number. Interactive terminals render subjects in ANSI bold; redirected output
contains no terminal control codes.

For a numbered message, the default display shows `To`, `From`, `Cc`,
`Subject`, and `Date` headers plus all non-attachment `text/plain` parts. If
no plain-text part exists, it renders non-attachment `text/html` parts to
plain text with Beautiful Soup. `--headers` includes every header; `--html`
prints decoded HTML parts; `--mime` prints the original RFC 5322/MIME source,
including all MIME parts and attachment encodings.

`mailsearch-gui` is a macOS-first, read-only pywebview consumer of the same
search and verified-message retrieval functions.  A single search field uses
the CLI selectors and ordinary ANDed terms; shell-style quotes group spaces,
so `subject:"annual report"` is one selector while `subject:annual report`
retains the CLI meaning of a subject selector plus a free-text term.  It loads
the newest 100 results at a time without changing the CLI's ten-result default.
Selecting a result shows it beside the list; double-clicking opens an
independent message window. The result list can sort by date, subject, or
sender in either direction. When it has keyboard focus, Up Arrow and Down
Arrow move the selection and display the newly selected message. Result rows
show the indexed attachment count with a paperclip.
An unchecked **Search attachments** control searches only headers and message
bodies. When checked, the same ordinary full-text expression also matches the
separate indexed text-attachment table; metadata selectors retain their normal
meaning. The control does not extract attachment content on demand.
The GUI paints each result page from header metadata first, then requests its
indexed body previews on a background worker and fills a reserved third line
without blocking the initial result display.

The GUI lists every non-attachment `text/plain` and `text/html` MIME part and
allows the user to select among them.  HTML is isolated and sanitized. Scripts,
forms, plugins, file URLs, and remote resources are blocked by default; remote
HTTP(S) images may load only after an explicit per-message action. Embedded
CID images may render from the verified message. Attachments appear in a list,
safe images and PDFs can be previewed inline, and opening any attachment is an
explicit action with an additional warning for executable or container types.
Command-1 through Command-9 select the MIME part having that numeric part ID;
Command-0 and Command-Shift-U select the raw RFC 5322 source.

Saving or dragging a message creates a disposable `.eml` copy containing the
exact SHA-256-verified RFC 5322 bytes; it never creates or changes canonical
archive content. Message headers remain selectable text. Dragging is confined
to a separate message-file icon well and is initially a macOS Finder
integration. Printing
prints the displayed headers and selected MIME part through the system print
panel. Temporary message and attachment exports are removed when the GUI exits.

`summarize` is an optional macOS command that reads nonempty UTF-8 text from
standard input and prints only a one-sentence Apple Intelligence summary of at
most 30 words to standard
output. It uses Apple's on-device Foundation Models framework, never writes the
input to the archive, and reports a clear error when the device is ineligible,
Apple Intelligence is disabled, or the model is not ready.

All archive commands use `MAIL_ARCHIVE_DIR` as their default archive directory.
`--archive DIRECTORY` overrides that environment variable. If neither is set,
the command fails before reading or writing an archive.

## Ingest sources

* Recursive local-directory ingest recognizes MBOX streams, Apple Mail MBOX
  packages, Maildir, individual RFC 5322 files, and Apple `.emlx` files.
  Local source-file fingerprints and append checkpoints use the physical file
  bytes, including `.emlx` trailing metadata even though it is not message data.
  Directory traversal must surface missing paths and permission failures rather
  than silently treating an unreadable mailbox as empty. Direct access to
  `~/Library/Mail` may require Full Disk Access for the invoking application.
* `.emlx` input uses its leading decimal byte count to select exactly the
  RFC 5322 message; Apple's trailing plist metadata is not part of the
  message hash or output. Apple `.partial.emlx` input is rejected because its
  attachment payloads are detached and reconstructing a message would not
  preserve the original RFC 5322 bytes. Apple Mail databases, plist files,
  attachment directories, and `.emlxpart` fragments are not separate messages.
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
* The MBOX byte hash, integrity files, locations, and metadata database updates are
  published transactionally.  Interrupted runs leave either the old verified
  archive or a recoverable temporary/backup pair; they never publish a partial
  archive as valid.
* Ingest installs `verify_mail_archive.py` in the archive. This single-file,
  standard-library-only tool is strictly read-only: it parses only the current
  `.mbox.integrity` format and verifies every declared complete-MBOX, raw-message,
  and semantic-message digest without consulting SQLite. It exits nonzero after
  reporting any mismatch.
* A future integrated `verify` command is strictly read-only: it reparses every canonical MBOX,
  checks integrity files, offsets, and database rows, and reports duplicate-policy
  violations.
* `refresh-index` rebuilds the disposable FTS database. `review` queries the
  committed source-observation log by run, source, and disposition. Derived
  catalog fields and canonical locations are created correctly during ingest.

## Scope boundaries

The first release is a local command-line normalizer and verifier.  Its TOML
configuration holds archive and scanner policy; `owner-names.txt` remains a
separate, one-name-per-line reusable classification input.  A local
special-purpose search and message-viewing interface is a consumer of
the two SQLite databases, not a reason to depend on Thunderbird or FoxTrot.
No source mailbox is modified by this program.
The current catalog schema is created only for a fresh archive and is versioned.
An unversioned or incompatible catalog is rejected. A fresh catalog is also
refused beside existing canonical MBOX or `.mbox.integrity` output because that
would defeat deduplication.
