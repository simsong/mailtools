"""Requirements: ingest progress remains visibly live during slow startup phases."""

from __future__ import annotations

import time

import pytest

from mailarchiver.__main__ import CLAMAV_START_PHASE, PROGRESS_REFRESH_SECONDS, ProgressReporter


def test_clamav_startup_wait_is_repeated_with_elapsed_time(capsys: pytest.CaptureFixture[str]) -> None:
    """Requirement: ClamAV startup emits a visible heartbeat every 250 milliseconds."""
    progress = ProgressReporter()
    progress.tty = False
    progress.start()
    try:
        progress.set_phase(CLAMAV_START_PHASE)
        time.sleep(PROGRESS_REFRESH_SECONDS * 2.5)
    finally:
        progress.finish("completed")

    lines = [line for line in capsys.readouterr().err.splitlines() if line.startswith(CLAMAV_START_PHASE)]
    assert len(lines) >= 3
    assert all("ClamAV daemon is loading virus definitions" in line for line in lines)
