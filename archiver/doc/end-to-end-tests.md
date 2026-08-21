# End-to-end acceptance tests

These black-box tests are intentionally written before the implementation.
They invoke `python -m mailarchiver` against a synthetic MBOX and a temporary
archive directory.  They must use the on-demand ClamAV configuration, not a
mock scanner.

`test_ingest_routes_preserves_and_indexes_messages` copies the checked-in
`tests/data/` three-message MBOX and three-record EMLX directory.  It covers raw-byte
preservation, Sent classification, exact deduplication, collision preservation,
autosave exclusion, path-year date fallback, invalid declared charset, ClamAV routing,
MBOX partitioning, manifests, metadata, FTS, and observations.
It also asserts the final real-time progress summary reports the processed
message and completed source-file counts.

`test_unchanged_source_files_are_skipped_wholesale` verifies full source-file
SHA-256 matches avoid per-message parsing, scanning, observations, and MBOX
changes. `test_mbox_append_resumes_after_verified_prefix` appends one complete
record and verifies only the new region is processed before the fingerprint is
updated. `test_malformed_subject_is_archived_with_metadata_defect` exercises
the observed invalid EUC-KR Base64 subject through the full ingest pipeline.

`test_report_counts_years_people_and_correspondents` checks the SQLite-only
report: year-level sent/received/unique-address totals and the optional top
sender and recipient lists for an inclusive year selection.

`test_interrupt_stops_cleanly` sends a real SIGINT to an active CLI subprocess
and asserts exit 130, a controlled interruption report, and no traceback.

`test_parser_failure_records_source_identity_and_failed_run` uses an undated
message with no path-year fallback and checks the failed run result plus the
error observation's source path, offset, raw SHA-256, and exception detail.
`test_fresh_catalog_is_refused_beside_existing_mbox` protects against deleting
only the database and accidentally appending duplicates to canonical output.

`test_publication.py` simulates process death after an MBOX append but before
catalog commit. Recovery must truncate exactly the orphaned record, retain
earlier bytes, and clear the durable journal; a catalogued append is retained
without depending on disposable search state.

`test_sources.py` verifies one sequential pass produces both the stored
old-length prefix SHA-256 and the updated complete-file SHA-256.

`test_message.py` checks earliest-valid-Received date fallback independently of
the MBOX/ClamAV integration corpus.

The tests are expected to fail until the first implementation phase supplies
the CLI, databases, and ingest pipeline.
