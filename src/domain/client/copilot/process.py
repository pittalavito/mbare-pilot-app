"""Running one Copilot invocation to the end: both pipes read in the
background, a timeout and a cancellation check; when stopped, Copilot and
whatever it started are killed."""
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import psutil

from domain.client.copilot.cli import NO_WINDOW

_POLL_SECONDS = 0.5


class StopReason(StrEnum):
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class ProcessResult:
    stdout: list[str]
    stderr: str
    returncode: int
    stopped: StopReason | None = None
    """Why the app stopped it; None when it ended on its own."""


def run(argv: list[str], cwd: Path, env: dict[str, str], timeout_seconds: float, should_cancel: Callable[[], bool]) -> ProcessResult:
    """Raises OSError when the process cannot start."""
    process = subprocess.Popen(
        argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        encoding="utf-8", errors="replace", env=env, **NO_WINDOW,
    )
    stdout, stderr = _PipeReader(process.stdout), _PipeReader(process.stderr)
    deadline = time.monotonic() + timeout_seconds
    stopped = None
    while process.poll() is None:
        if should_cancel():
            stopped = StopReason.CANCELLED
        elif time.monotonic() > deadline:
            stopped = StopReason.TIMEOUT
        if stopped:
            _kill_tree(process)
            break
        time.sleep(_POLL_SECONDS)
    process.wait()
    stdout.join(), stderr.join()
    return ProcessResult(stdout=stdout.lines, stderr="".join(stderr.lines), returncode=process.returncode, stopped=stopped)


class _PipeReader(threading.Thread):
    """Reads a pipe to the end in the background, so a full pipe never blocks Copilot."""

    def __init__(self, pipe):
        super().__init__(daemon=True)
        self.lines: list[str] = []
        self._pipe = pipe
        self.start()

    def run(self) -> None:
        for line in self._pipe:
            self.lines.append(line)


def _kill_tree(process: subprocess.Popen) -> None:
    """Copilot and whatever it started (shells, test runs...)."""
    try:
        parent = psutil.Process(process.pid)
        for child in parent.children(recursive=True):
            child.kill()
        parent.kill()
    except psutil.NoSuchProcess:
        pass
