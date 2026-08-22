# AI contributor instructions

## Scope and source safety

`archiver/` creates a personal, long-lived email archive.  Its canonical
content is standard MBOX plus SHA-256 manifests; SQLite databases and search
indexes are rebuildable derivatives.

* Never modify, delete, move, label, mark read, or otherwise mutate a source
  mailbox, Gmail account, IMAP account, Apple Mail store, or input archive.
* Preserve original RFC 5322 bytes.  MIME parsing, text extraction, malformed
  MIME handling, and Unicode decoding are best-effort derived operations and
  must never cause a message to be dropped or rewritten.
* A positive ClamAV result routes a message to `INFECTED.mbox`; it is not a
  reason to delete or alter the message.  Scanner errors and unscannable input
  must be recorded and retained.
* Do not ingest into a real canonical archive until the user identifies the
  target directory and explicitly authorizes that run.  Develop and validate
  against purpose-made fixtures or a copied subset.
* Do not alter local machine configuration, install software, start a
  persistent service, or schedule jobs without explicit user approval.  The
  ClamAV daemon is on-demand only; never enable on-access or scheduled scans.

## Requirements and documentation

Before implementing a behavior change, read `archiver/doc/requirements.md`
and `archiver/doc/implementation.md`.  Update both in the same change when
behavior, archive format, recovery semantics, database schema, CLI, or source
support changes.

Keep these documents factual and compact.  Document the relevant requirement
next to each substantive test or test module.  Never claim a feature works
merely because it compiles or emits output: confirm that validation exercises
the stated requirement and report any remaining gap.

## Python implementation

* Use Python 3.12+ and `uv`; add project dependencies through `uv`, not pip.
* All ordinary test and run workflows belong in the Makefile.  Use `make
  check` for the full suite; add focused targets only when they validate a
  distinct real behavior.
* Prefer standard-library `mailbox.mbox` for MBOX reading and writing.  Pass
  raw `bytes`, not reserialized `email.message.Message` objects, when writing
  archived messages.
* Use typed Pydantic models for internal data.  Restrict dictionaries to
  external API boundaries and put external keys in named constants.
* Keep file and database I/O streaming; do not load an archive or attachments
  wholesale into memory.
* Use SHA-256 for canonical message and manifest hashes.  Do not substitute a
  hash algorithm, data source, parser, or archive format without explicit user
  approval.

## Tests and validation

Write only substantive tests that test a requirement or a demonstrated
regression.  No coverage-only tests and no mocks unless unavoidable.

Fixtures must cover byte preservation, mboxrd quoting, malformed MIME,
invalid character encodings, missing dates, duplicate Message-ID with
different content, autosave exclusion, rollover, interruption recovery, and
source idempotence.  Use EICAR with the locally configured on-demand ClamAV
daemon for the scanner integration test; use recorded typed scan results only
for unit-level routing tests.

Before reporting a phase complete, review the changed implementation and
tests against every relevant requirement, run the appropriate Makefile target,
and distinguish validated behavior from untested assumptions.

## Git and external actions

Preserve dirty worktrees and unrelated changes.  Use project-local linked
worktrees under `<project-root>/.tmp/` for branch work.

Do not commit, push, open or modify pull requests, approve, merge, close
issues, or change remote services unless the user explicitly requests it.
When authorized, Codex GitHub activity uses `@simsong-codex`; signed commits
use `Codex AI Assistant <simsong+codex@acm.org>` and the configured Codex GPG
key.  Verify identity and signature after committing.
