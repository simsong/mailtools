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
message count.

`test_rerun_is_idempotent_and_reviewable` covers message-level idempotence and
the reviewable observation log.  It asserts that rerunning an unchanged source
does not alter canonical MBOX files or add logical messages, while it records
a second ingest run and source observations.

`test_report_counts_years_people_and_correspondents` checks the SQLite-only
report: year-level sent/received/unique-address totals and the optional top
sender and recipient lists for an inclusive year selection.

`test_interrupt_stops_cleanly` sends a real SIGINT to an active CLI subprocess
and asserts exit 130, a controlled interruption report, and no traceback.

`test_parser_failure_records_source_identity_and_failed_run` uses an undated
message with no path-year fallback and checks the failed run result plus the
error observation's source path, offset, raw SHA-256, and exception detail.

`test_message.py` checks earliest-valid-Received date fallback independently of
the MBOX/ClamAV integration corpus.

The tests are expected to fail until the first implementation phase supplies
the CLI, databases, and ingest pipeline.
