"""Requirements: summarize consumes nonempty standard input without changing archives."""

from __future__ import annotations

import subprocess
import sys


def test_summarize_rejects_empty_input_before_native_model_work() -> None:
    """Requirement: empty input is a usage error and produces no summary."""
    completed = subprocess.run(
        [sys.executable, "-m", "mailarchiver.aisummarize"],
        input=" \n",
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr == "summarize: standard input is empty\n"
