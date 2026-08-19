"""On-demand ClamAV process management."""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
from contextlib import AbstractContextManager
from pathlib import Path


CLAMD = os.environ.get("MAILARCHIVER_CLAMD", "/opt/homebrew/sbin/clamd")
CLAMDSCAN = os.environ.get("MAILARCHIVER_CLAMDSCAN", "/opt/homebrew/bin/clamdscan")
CLAMD_CONFIG = os.environ.get("MAILARCHIVER_CLAMD_CONFIG", "/opt/homebrew/etc/clamav/clamd.conf")
CLAMD_SOCKET = Path(os.environ.get("MAILARCHIVER_CLAMD_SOCKET", "/private/tmp/clamd.sock"))
CLAMD_START_TIMEOUT_SECONDS = 120


class ClamScanner(AbstractContextManager["ClamScanner"]):
    """Use an existing daemon or one temporary daemon for one ingest run."""

    def __init__(self) -> None:
        self.process: subprocess.Popen[bytes] | None = None

    def __enter__(self) -> "ClamScanner":
        if CLAMD_SOCKET.exists() and self.available():
            return self
        CLAMD_SOCKET.unlink(missing_ok=True)
        self.process = subprocess.Popen([CLAMD, "--foreground", f"--config-file={CLAMD_CONFIG}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(CLAMD_START_TIMEOUT_SECONDS * 10):
                if CLAMD_SOCKET.exists():
                    return self
                if self.process.poll() is not None:
                    raise RuntimeError("clamd failed to start; inspect its configuration")
                time.sleep(0.1)
        except BaseException:
            self.__exit__()
            raise
        self.__exit__()
        raise RuntimeError("timed out waiting for clamd socket")

    def __exit__(self, *_: object) -> None:
        if self.process is not None:
            self.process.terminate()
            self.process.wait(timeout=10)
            CLAMD_SOCKET.unlink(missing_ok=True)

    @staticmethod
    def available() -> bool:
        return subprocess.run([CLAMDSCAN, f"--config-file={CLAMD_CONFIG}", "--ping=1"], check=False, capture_output=True).returncode == 0

    def infected(self, raw: bytes) -> bool:
        with tempfile.NamedTemporaryFile(prefix="mailarchiver-", delete=False) as handle:
            handle.write(raw)
            temporary = handle.name
        try:
            result = subprocess.run([CLAMDSCAN, f"--config-file={CLAMD_CONFIG}", "--stream", temporary], check=False, capture_output=True)
            if result.returncode not in (0, 1):
                raise RuntimeError(result.stderr.decode("utf-8", "replace"))
            return result.returncode == 1
        finally:
            os.unlink(temporary)
