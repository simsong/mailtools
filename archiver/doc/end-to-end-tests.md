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

`test_rerun_is_idempotent_and_reviewable` covers message-level idempotence and
the reviewable observation log.  It asserts that rerunning an unchanged source
does not alter canonical MBOX files or add logical messages, while it records
a second ingest run and source observations.

`test_report_counts_years_people_and_correspondents` checks the SQLite-only
report: year-level sent/received/unique-address totals and the optional top
sender and recipient lists for an inclusive year selection.

The tests are expected to fail until the first implementation phase supplies
the CLI, databases, and ingest pipeline.
