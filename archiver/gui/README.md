# Mail archive GUI prototype

This macOS-first pywebview prototype searches an existing mailarchiver archive.
It does not ingest mail or modify the archive.

Run it from `archiver/`:

```console
uv sync
make gui ARGS="--archive /path/to/archive"
```

The archive must contain `archive.sqlite3`, `search.sqlite3`, and the canonical
MBOX files referenced by the catalog. Without `--archive`, the app opens with a
directory chooser.

This prototype revision adds attachment metadata, deterministic 18-word body
previews, and a separate text-attachment FTS table to the disposable search
database. Build the index before using the GUI; include
`--index-attachments` to populate attachment search:

```console
make run ARGS="--archive /path/to/archive refresh-index --index-attachments"
```

The prototype provides one-field CLI-compatible search, an explicit **Search
attachments** checkbox, 100-result paging,
date/subject/sender sorting, keyboard result navigation, MIME-part shortcuts,
message and MIME-part views, separate message windows, sanitized HTML with
remote content blocked by default, inline image and PDF previews, attachment
open/save actions, printing, exact `.eml` export, and experimental Finder
drag-out from a result or the dedicated message-file well.

Automated tests verify search parsing, MIME selection, HTML sanitization,
remote-content blocking, exact message export, decoded attachment export, and
risky attachment classification. Native dialogs, printing, external attachment
opening, PDF rendering, and Finder drag-out still require manual macOS tests.
Run `make gui-smoke` on macOS to verify the JavaScript-to-Python bridge.
