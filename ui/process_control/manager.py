"""Starts and stops backend processes (API, worker) from the UI, on this PC.

A started process outlives Streamlit reruns and restarts: its PID (plus its
start time, so a reused PID is never mistaken for it) is kept in
``<run_dir>/<name>.pid`` and its output in ``<log_dir>/<name>.log``. Stopping
kills the whole process tree. A service with a ``health_url`` that answers
while no PID is known was started elsewhere (e.g. a terminal): it is reported
as EXTERNAL and never stopped from here."""
import os
import subprocess
import sys
from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import httpx
import psutil

_HEALTH_TIMEOUT = 1.5
_STOP_TIMEOUT = 5.0


class ServiceStatus(StrEnum):
    RUNNING = "running"
    STARTING = "starting"
    """Process alive, health check not answering yet."""
    STOPPED = "stopped"
    EXTERNAL = "external"
    """Healthy but not started by the UI."""


@dataclass(frozen=True)
class ManagedService:
    name: str
    """File-safe id: ``api``, ``worker``."""
    label: str
    command: list[str]
    health_url: str | None = None
    """When set, RUNNING also requires a 2xx here."""
    env: dict[str, str] = field(default_factory=dict)
    """Extra environment variables for the process."""


class ProcessManager:

    def __init__(self, cwd: Path, run_dir: Path, log_dir: Path):
        self._cwd = cwd
        self._run_dir = run_dir
        self._log_dir = log_dir

    # ----------------------------------------------------------- queries
    def status(self, service: ManagedService) -> ServiceStatus:
        process = self._process(service)
        healthy = self._healthy(service)
        if process is None:
            return ServiceStatus.EXTERNAL if healthy else ServiceStatus.STOPPED
        if service.health_url and not healthy:
            return ServiceStatus.STARTING
        return ServiceStatus.RUNNING

    def pid(self, service: ManagedService) -> int | None:
        process = self._process(service)
        return process.pid if process else None

    def logs(self, service: ManagedService, lines: int = 40) -> str:
        path = self._log_path(service)
        if not path.is_file():
            return ""
        with path.open(encoding="utf-8", errors="replace") as handle:
            return "".join(deque(handle, maxlen=lines))

    # ----------------------------------------------------------- actions
    def start(self, service: ManagedService) -> int:
        """Start the process (no-op when already started here). Returns its PID.
        Raises RuntimeError when the service is already running elsewhere."""
        process = self._process(service)
        if process is not None:
            return process.pid
        if self._healthy(service):
            raise RuntimeError(f"{service.label} è già attiva, avviata fuori dall'app: fermala da lì.")
        self._run_dir.mkdir(parents=True, exist_ok=True)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        with self._log_path(service).open("ab") as log:
            popen = subprocess.Popen(
                service.command, cwd=self._cwd, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                env={**os.environ, "PYTHONUNBUFFERED": "1", **service.env},
                **_detached(),
            )
        started = psutil.Process(popen.pid).create_time()
        self._pid_path(service).write_text(f"{popen.pid} {started}", encoding="utf-8")
        return popen.pid

    def stop(self, service: ManagedService) -> bool:
        """Kill the process tree started here. False when there was none."""
        process = self._process(service)
        self._pid_path(service).unlink(missing_ok=True)
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
    def _process(self, service: ManagedService) -> psutil.Process | None:
        """The live process recorded in the PID file; clears a stale file."""
        path = self._pid_path(service)
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

    @staticmethod
    def _healthy(service: ManagedService) -> bool:
        if not service.health_url:
            return False
        try:
            return httpx.get(service.health_url, timeout=_HEALTH_TIMEOUT).is_success
        except httpx.HTTPError:
            return False

    def _pid_path(self, service: ManagedService) -> Path:
        return self._run_dir / f"{service.name}.pid"

    def _log_path(self, service: ManagedService) -> Path:
        return self._log_dir / f"{service.name}.log"


def _detached() -> dict:
    """Keep the child alive and out of reach of Ctrl+C in the Streamlit terminal."""
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
    return {"start_new_session": True}
