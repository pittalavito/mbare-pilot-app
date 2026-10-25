"""Starts and stops the app's own background processes (the worker) on this PC.

A started process outlives the API's restarts: its PID (plus its start time,
so a reused PID is never mistaken for it) is kept in ``<run_dir>/<name>.pid``
and its output in ``<log_dir>/<name>.log``. Stopping kills its whole tree."""
import os
import subprocess
import sys
from collections import deque
from pathlib import Path

import psutil
from dotenv import dotenv_values

_STOP_TIMEOUT = 5.0


class ProcessManager:

    def __init__(self, cwd: Path, run_dir: Path, log_dir: Path):
        self._cwd = cwd
        self._run_dir = run_dir
        self._log_dir = log_dir

    # ----------------------------------------------------------- queries
    def pid(self, name: str) -> int | None:
        """The PID of the live process started here as ``name``; None when there is none."""
        process = self._process(name)
        return process.pid if process else None

    def logs(self, name: str, lines: int = 200) -> str:
        """The last ``lines`` lines of the process' log ('' when it has none)."""
        path = self._log_dir / f"{name}.log"
        if not path.is_file():
            return ""
        with path.open(encoding="utf-8", errors="replace") as handle:
            return "".join(deque(handle, maxlen=lines))

    # ----------------------------------------------------------- actions
    def start(self, name: str, command: list[str]) -> int:
        """Start ``command`` as ``name`` (no-op when already running). Returns its PID."""
        process = self._process(name)
        if process is not None:
            return process.pid
        self._run_dir.mkdir(parents=True, exist_ok=True)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        with (self._log_dir / f"{name}.log").open("ab") as log:
            popen = subprocess.Popen(
                command, cwd=self._cwd, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                env={**os.environ, **self._dotenv(), "PYTHONUNBUFFERED": "1"},
                **_detached(),
            )
        started = psutil.Process(popen.pid).create_time()
        self._pid_path(name).write_text(f"{popen.pid} {started}", encoding="utf-8")
        return popen.pid

    def stop(self, name: str) -> bool:
        """Kill the process tree started here as ``name``. False when there was none."""
        process = self._process(name)
        self._pid_path(name).unlink(missing_ok=True)
        if process is None:
            return False
        tree = [*process.children(recursive=True), process]
        for member in tree:
            try:
                member.terminate()
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs(tree, timeout=_STOP_TIMEOUT)
        for member in alive:
            try:
                member.kill()
            except psutil.NoSuchProcess:
                pass
        return True

    # ----------------------------------------------------------- helpers
    def _process(self, name: str) -> psutil.Process | None:
        """The live process recorded in the PID file; clears a stale file."""
        path = self._pid_path(name)
        if not path.is_file():
            return None
        try:
            pid_text, started_text = path.read_text(encoding="utf-8").split()
            process = psutil.Process(int(pid_text))
            if abs(process.create_time() - float(started_text)) < 1 and process.status() != psutil.STATUS_ZOMBIE:
                return process
        except (ValueError, psutil.Error):
            pass
        path.unlink(missing_ok=True)
        return None

    def _dotenv(self) -> dict[str, str]:
        """The .env read now: a process started later sees the current values
        (e.g. a key changed meanwhile), not those loaded when the API started."""
        return {key: value for key, value in dotenv_values(self._cwd / ".env").items() if value is not None}

    def _pid_path(self, name: str) -> Path:
        return self._run_dir / f"{name}.pid"


def _detached() -> dict:
    """Keep the child alive on its own, out of reach of Ctrl+C in a terminal. On
    Windows a hidden console of its own is enough (no CREATE_NEW_PROCESS_GROUP)."""
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {"start_new_session": True}
