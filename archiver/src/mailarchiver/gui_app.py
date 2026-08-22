"""macOS-first pywebview shell for read-only archive search."""

from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from typing import Any

import webview
from pydantic import BaseModel

from .gui_service import (
    AttachmentContent,
    MessageView,
    MessagePreview,
    PreviewBatch,
    attachment_content,
    describe_message,
    export_filename,
    is_risky,
    message_previews,
    render_part,
    safe_filename,
    search_page,
    write_attachment,
    write_message,
)

GUI_DIRECTORY = Path(__file__).parents[2] / "gui"
DEFAULT_PAGE_SIZE = 100


class GuiStatus(BaseModel):
    archive: str | None
    ready: bool


class DragExport(BaseModel):
    filename: str
    url: str


class OpenResult(BaseModel):
    opened: bool = False
    requires_confirmation: bool = False
    filename: str


class GuiApi:
    """Narrow API exposed to one webview window."""

    def __init__(self, archive: Path | None, temporary_directory: Path | None = None) -> None:
        self.archive = archive
        self.window: Any = None
        self._temporary = tempfile.TemporaryDirectory(prefix="mailarchive-gui-") if temporary_directory is None else None
        self.temporary_directory = Path(self._temporary.name) if self._temporary else temporary_directory
        self.children: list[GuiApi] = []
        self._preview_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mail-preview")
        self._preview_lock = Lock()
        self._preview_cache: dict[int, MessagePreview] = {}
        self._preview_pending: set[int] = set()
        self._preview_error: str | None = None
        self._preview_generation = 0

    def set_window(self, window: Any) -> None:
        self.window = window

    def status(self) -> dict[str, object]:
        ready = self.archive is not None and _is_archive(self.archive)
        return GuiStatus(archive=str(self.archive) if self.archive else None, ready=ready).model_dump()

    def choose_archive(self) -> dict[str, object]:
        selected = self.window.create_file_dialog(webview.FileDialog.FOLDER, directory=str(Path.home()))
        if selected:
            archive = Path(selected[0])
            if not _is_archive(archive):
                raise ValueError(f"{archive} must contain archive.sqlite3 and search.sqlite3")
            self.archive = archive
            with self._preview_lock:
                self._preview_generation += 1
                self._preview_cache.clear()
                self._preview_pending.clear()
                self._preview_error = None
        return self.status()

    def search(
        self,
        query: str,
        offset: int = 0,
        sort_by: str = "date",
        direction: str = "descending",
        search_attachments: bool = False,
    ) -> dict[str, object]:
        return search_page(
            self._archive(), query, offset, DEFAULT_PAGE_SIZE, sort_by, direction, search_attachments
        ).model_dump(mode="json")

    def request_previews(self, message_pks: list[int]) -> bool:
        if not message_pks or len(message_pks) > DEFAULT_PAGE_SIZE:
            raise ValueError(f"request between 1 and {DEFAULT_PAGE_SIZE} message previews")
        with self._preview_lock:
            requested = set(message_pks)
            missing = requested - self._preview_cache.keys() - self._preview_pending
            self._preview_pending.update(missing)
            self._preview_error = None
        if missing:
            archive = self._archive()
            generation = self._preview_generation
            self._preview_executor.submit(self._load_previews, archive, sorted(missing), generation)
        return True

    def take_previews(self, message_pks: list[int]) -> dict[str, object]:
        requested = set(message_pks)
        with self._preview_lock:
            previews = [self._preview_cache[message_pk] for message_pk in message_pks if message_pk in self._preview_cache]
            batch = PreviewBatch(
                previews=previews,
                pending=bool(requested & self._preview_pending),
                error=self._preview_error,
            )
        return batch.model_dump(mode="json")

    def _load_previews(self, archive: Path, message_pks: list[int], generation: int) -> None:
        try:
            previews = message_previews(archive, message_pks)
            with self._preview_lock:
                if generation == self._preview_generation and archive == self.archive:
                    self._preview_cache.update((preview.message_pk, preview) for preview in previews)
        except Exception as error:  # pylint: disable=broad-exception-caught
            with self._preview_lock:
                if generation == self._preview_generation:
                    self._preview_error = f"{type(error).__name__}: {error}"
        finally:
            with self._preview_lock:
                if generation == self._preview_generation:
                    self._preview_pending.difference_update(message_pks)

    def message(self, message_pk: int) -> dict[str, object]:
        return describe_message(self._archive(), message_pk).model_dump(mode="json")

    def part(self, message_pk: int, part_id: int, allow_remote: bool = False) -> dict[str, object]:
        return render_part(self._archive(), message_pk, part_id, allow_remote).model_dump(mode="json")

    def attachment(self, message_pk: int, part_id: int) -> dict[str, object]:
        return attachment_content(self._archive(), message_pk, part_id).model_dump(mode="json")

    def save_message(self, message_pk: int) -> str | None:
        view = describe_message(self._archive(), message_pk)
        selected = self.window.create_file_dialog(
            webview.FileDialog.SAVE,
            directory=str(Path.home() / "Desktop"),
            save_filename=export_filename(view),
            file_types=("Email message (*.eml)",),
        )
        if not selected:
            return None
        destination = Path(selected[0])
        if destination.suffix.casefold() != ".eml":
            destination = destination.with_suffix(".eml")
        write_message(self._archive(), message_pk, destination)
        return str(destination)

    def save_attachment(self, message_pk: int, part_id: int) -> str | None:
        attachment = attachment_content(self._archive(), message_pk, part_id)
        selected = self.window.create_file_dialog(
            webview.FileDialog.SAVE,
            directory=str(Path.home() / "Desktop"),
            save_filename=attachment.filename,
            file_types=("All files (*.*)",),
        )
        if not selected:
            return None
        destination = Path(selected[0])
        write_attachment(self._archive(), message_pk, part_id, destination)
        return str(destination)

    def prepare_drag(self, message_pk: int) -> dict[str, str]:
        view = describe_message(self._archive(), message_pk)
        destination = self.temporary_directory / export_filename(view)
        write_message(self._archive(), message_pk, destination)
        return DragExport(filename=destination.name, url=destination.as_uri()).model_dump()

    def open_attachment(self, message_pk: int, part_id: int, confirmed: bool = False) -> dict[str, object]:
        content: AttachmentContent = attachment_content(self._archive(), message_pk, part_id)
        risky = is_risky(content.filename, content.content_type)
        if risky and not confirmed:
            return OpenResult(filename=content.filename, requires_confirmation=True).model_dump()
        destination = self.temporary_directory / safe_filename(content.filename, part_id, content.content_type)
        write_attachment(self._archive(), message_pk, part_id, destination)
        subprocess.Popen(["/usr/bin/open", str(destination)], close_fds=True)
        return OpenResult(filename=content.filename, opened=True).model_dump()

    def open_message_window(self, message_pk: int) -> None:
        view: MessageView = describe_message(self._archive(), message_pk)
        base_url = str(self.window.get_current_url()).split("?", 1)[0]
        child_api = GuiApi(self._archive(), self.temporary_directory)
        child = webview.create_window(
            view.subject,
            f"{base_url}?message={message_pk}&standalone=1",
            js_api=child_api,
            width=900,
            height=760,
            min_size=(560, 420),
            text_select=True,
            draggable=True,
        )
        child_api.set_window(child)
        self.children.append(child_api)

    def close(self, *_args: object) -> None:
        self._preview_executor.shutdown(wait=False, cancel_futures=True)
        if self._temporary:
            self._temporary.cleanup()

    def _archive(self) -> Path:
        if self.archive is None or not _is_archive(self.archive):
            raise ValueError("choose an archive containing archive.sqlite3 and search.sqlite3")
        return self.archive


def _is_archive(path: Path) -> bool:
    return path.is_dir() and (path / "archive.sqlite3").is_file() and (path / "search.sqlite3").is_file()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only graphical search of a mailarchiver archive.")
    parser.add_argument("--archive", type=Path, help="directory containing archive.sqlite3 and search.sqlite3")
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    return parser


def verify_bridge(window: Any, result: list[str]) -> None:
    """Call the exposed Python API from JavaScript, then close the smoke-test window."""
    try:
        has_api = window.evaluate_js("typeof window.pywebview?.api?.status === 'function'")
        if not has_api:
            raise RuntimeError("pywebview API was not injected")
        window.run_js(
            "window.__mailarchiveSmoke = 'waiting';"
            "window.pywebview.api.status().then(function(value) {"
            "window.__mailarchiveSmoke = Object.hasOwn(value, 'ready') ? 'passed' : 'invalid';"
            "}).catch(function(error) { window.__mailarchiveSmoke = 'failed: ' + error; });"
        )
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = window.evaluate_js("window.__mailarchiveSmoke")
            if state == "passed":
                result.append("passed")
                return
            if isinstance(state, str) and state not in {"waiting", "passed"}:
                raise RuntimeError(state)
            time.sleep(0.05)
        raise RuntimeError("status API call timed out")
    except Exception as error:  # pylint: disable=broad-exception-caught
        result.append(str(error))
    finally:
        window.destroy()


def main() -> int:
    args = build_parser().parse_args()
    archive_value = os.environ.get("MAIL_ARCHIVE_DIR")
    archive = args.archive or (Path(archive_value) if archive_value else None)
    if archive is not None and not _is_archive(archive):
        raise SystemExit(f"mailsearch-gui: {archive} must contain archive.sqlite3 and search.sqlite3")
    api = GuiApi(archive)
    window = webview.create_window(
        "Mail Archive",
        str(GUI_DIRECTORY / "index.html"),
        js_api=api,
        width=1400,
        height=900,
        min_size=(900, 560),
        text_select=True,
        draggable=True,
    )
    api.set_window(window)
    window.events.closed += api.close
    smoke_result: list[str] = []
    if args.smoke_test:
        window.events.loaded += lambda *_args: verify_bridge(window, smoke_result)
    webview.settings["ALLOW_FILE_URLS"] = True
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    webview.start(http_server=True, private_mode=True)
    if args.smoke_test:
        passed = smoke_result == ["passed"]
        print("GUI bridge smoke test passed" if passed else f"GUI bridge smoke test failed: {smoke_result}")
        return 0 if passed else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
