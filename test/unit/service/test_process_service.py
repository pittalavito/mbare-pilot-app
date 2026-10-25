"""The worker started and stopped by the API, with a real (dummy) child process,
and seen through its heartbeat when started elsewhere; the processes' logs."""
import sys
import time
from datetime import datetime, timezone

import psutil
import pytest

from core.error import ConflictError
from domain.process.manager import ProcessManager
from models.domain.process import ProcessName, WorkerProcessStatus
from models.domain.worker import WorkerStatus
from service.process_service import ProcessService

_SLEEPER = [sys.executable, "-c", "import time; print('worker pronto', flush=True); time.sleep(60)"]


class _Pipelines:
    """Stands in for PipelineService: the workers sending their heartbeat."""

    def __init__(self):
        self.heartbeats: list[WorkerStatus] = []

    def workers(self) -> list[WorkerStatus]:
        return self.heartbeats


@pytest.fixture
def pipelines():
    return _Pipelines()


@pytest.fixture
def service(tmp_path, pipelines):
    manager = ProcessManager(cwd=tmp_path, run_dir=tmp_path / "run", log_dir=tmp_path / "logs")
    service = ProcessService(pipelines, manager, _SLEEPER)
    yield service
    manager.stop(ProcessName.WORKER)  # never leave processes behind


def _wait_for(predicate, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return False


def _heartbeat() -> WorkerStatus:
    now = datetime.now(timezone.utc)
    return WorkerStatus(worker_id="pc-1", host="pc", pid=1, started_at=now, last_seen=now)


def test_start_logs_stop(service):
    assert service.worker().status is WorkerProcessStatus.STOPPED

    state = service.start_worker()

    assert state.status is WorkerProcessStatus.RUNNING and psutil.pid_exists(state.pid)
    assert service.start_worker().pid == state.pid  # already running: no second process
    assert _wait_for(lambda: "worker pronto" in service.logs(ProcessName.WORKER))

    assert service.stop_worker().status is WorkerProcessStatus.STOPPED
    assert _wait_for(lambda: not psutil.pid_exists(state.pid) or psutil.Process(state.pid).status() == psutil.STATUS_ZOMBIE)


def test_a_worker_started_elsewhere_is_seen_and_not_started_twice(service, pipelines):
    pipelines.heartbeats = [_heartbeat()]

    state = service.worker()

    assert (state.status, state.pid, len(state.workers)) == (WorkerProcessStatus.EXTERNAL, None, 1)
    with pytest.raises(ConflictError, match="fuori dall'app"):
        service.start_worker()


def test_a_process_without_a_log_has_empty_logs(service):
    assert service.logs(ProcessName.API) == ""


def test_the_processes_live_in_the_app_folder(config):
    assert (config.app_root / config.worker_script).is_file()
    assert (config.run_dir, config.logs_dir) == (config.app_root / "resource" / "run", config.app_root / "resource" / "logs")
