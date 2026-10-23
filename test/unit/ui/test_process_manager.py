"""ProcessManager with real (dummy) child processes: start, status, logs,
stop of the whole tree, stale PID files, services started elsewhere."""
import sys
import time

import psutil
import pytest

from process_control.manager import ManagedService, ProcessManager, ServiceStatus
from process_control.services import backend_services

_SLEEPER = [sys.executable, "-c", "import time; print('ciao', flush=True); time.sleep(60)"]
_WITH_CHILD = [sys.executable, "-c", (
    "import subprocess, sys, time; "
    "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
    "print('padre', flush=True); time.sleep(60)"
)]


@pytest.fixture
def manager(tmp_path):
    manager = ProcessManager(cwd=tmp_path, run_dir=tmp_path / "run", log_dir=tmp_path / "logs")
    yield manager
    for name in ("sleeper", "tree", "api"):  # never leave processes behind
        manager.stop(ManagedService(name=name, label=name, command=[]))


def _wait_for(predicate, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return False


def test_start_status_logs_stop(manager):
    service = ManagedService(name="sleeper", label="Sleeper", command=_SLEEPER)
    assert manager.status(service) is ServiceStatus.STOPPED

    pid = manager.start(service)

    assert manager.status(service) is ServiceStatus.RUNNING and manager.pid(service) == pid
    assert manager.start(service) == pid  # already running: no second process
    assert _wait_for(lambda: "ciao" in manager.logs(service))

    assert manager.stop(service) is True
    assert _wait_for(lambda: not psutil.pid_exists(pid) or psutil.Process(pid).status() == psutil.STATUS_ZOMBIE)
    assert manager.status(service) is ServiceStatus.STOPPED
    assert manager.stop(service) is False


def test_stop_kills_the_whole_tree(manager):
    service = ManagedService(name="tree", label="Tree", command=_WITH_CHILD)
    pid = manager.start(service)
    assert _wait_for(lambda: len(psutil.Process(pid).children(recursive=True)) >= 1)
    children = [child.pid for child in psutil.Process(pid).children(recursive=True)]

    manager.stop(service)

    for child in children:
        assert _wait_for(lambda c=child: not psutil.pid_exists(c) or psutil.Process(c).status() == psutil.STATUS_ZOMBIE)


def test_stale_or_garbage_pid_file_means_stopped(manager, tmp_path):
    service = ManagedService(name="sleeper", label="Sleeper", command=_SLEEPER)
    (tmp_path / "run").mkdir()
    pid_file = tmp_path / "run" / "sleeper.pid"

    pid_file.write_text(f"{psutil.Process().pid} 1.0", encoding="utf-8")  # live PID, wrong start time
    assert manager.status(service) is ServiceStatus.STOPPED and not pid_file.exists()

    pid_file.write_text("not a pid", encoding="utf-8")
    assert manager.status(service) is ServiceStatus.STOPPED and not pid_file.exists()


def test_health_check_decides_starting_running_and_external(manager, monkeypatch):
    service = ManagedService(name="api", label="API", command=_SLEEPER, health_url="http://api.test/health")
    healthy = {"value": True}
    monkeypatch.setattr(ProcessManager, "_healthy", staticmethod(lambda s: healthy["value"]))

    assert manager.status(service) is ServiceStatus.EXTERNAL
    with pytest.raises(RuntimeError, match="fuori dall'app"):
        manager.start(service)

    healthy["value"] = False
    manager.start(service)
    assert manager.status(service) is ServiceStatus.STARTING
    healthy["value"] = True
    assert manager.status(service) is ServiceStatus.RUNNING


def test_backend_services_follow_the_api_url():
    api, worker = backend_services("http://127.0.0.1:8010")

    assert api.health_url == "http://127.0.0.1:8010/health"
    assert api.command[-4:] == ["--host", "127.0.0.1", "--port", "8010"]
    assert worker.command[-1] == "src/worker.py" and worker.health_url is None
