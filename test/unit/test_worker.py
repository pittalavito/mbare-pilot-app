"""The worker's Copilot lanes: each claimed job runs in its own thread, so
jobs run in parallel and the heartbeat lists them while they run."""
import threading

import pytest

import worker
from models.domain.copilot import CopilotSession


class _Pipelines:
    """What the heartbeat needs of PipelineService: it records the beats."""

    def __init__(self):
        self.beats = []

    def heartbeat(self, status):
        self.beats.append(list(status.busy_copilot_session_ids))

    def worker_stopped(self, worker_id):
        pass


class _Stop(BaseException):
    """Ends the lane's endless loop (not an Exception: the lane would log and go on)."""


def test_a_copilot_lane_runs_its_jobs_in_parallel(monkeypatch):
    monkeypatch.setattr(worker, "_POLL_SECONDS", 0)
    pipelines = _Pipelines()
    heartbeat = worker._Heartbeat(pipelines)
    sessions = [CopilotSession(id=id_, project_name="acme", task_note="t.md", copilot_session_id=str(id_)) for id_ in (1, 2)]
    together = threading.Barrier(3, timeout=10)  # both jobs and the test: only if they run at the same time
    finished = threading.Barrier(3, timeout=10)

    def claim():
        if sessions:
            return sessions.pop(0)
        together.wait()
        raise _Stop

    def run(session):
        together.wait()
        finished.wait()

    with pytest.raises(_Stop):
        worker._copilot_lane("test", claim, run, heartbeat)
    assert heartbeat.status.busy_copilot_session_ids == [1, 2]  # both running
    finished.wait()
    for thread in [thread for thread in threading.enumerate() if thread.name.startswith("copilot-test-")]:
        thread.join(timeout=10)
    assert heartbeat.status.busy_copilot_session_ids == [] and [1, 2] in pipelines.beats
