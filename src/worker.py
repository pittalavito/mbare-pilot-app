"""Automation worker: a process apart from the API that executes the queues.
Started by the API from the app's header (or `python src/worker.py`); more
workers can run together (the queues never hand a job to two of them).

Three lanes, independent of each other, so none waits for another:

- **automation**: the queued pipeline runs, one at a time (the main thread);
- **Copilot executions**: each in its own thread, in parallel; the queue hands
  out only executions whose repositories are all free (one per repository);
- **Copilot planning turns**: each in its own thread, in parallel (plan mode
  only reads: they wait for nothing).

While alive it beats every few seconds in Redis (also during a long run, from
a background thread), so the API knows which workers are running and what
they are doing; a worker that dies stops beating and disappears.

Each job remembers the worker that took it (``claimed_by``). At its start and
then every ``_REAP_SECONDS`` a worker fails the ``running`` jobs whose worker
is no longer beating: it died, they would stay stuck. Jobs of the workers still
beating are never touched, so more workers can run together.

    python src/worker.py
"""
import os
import socket
import threading
import time
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from typing import Protocol

from config import Config
from core.container import Container
from core.observability import LogPrefix, configure_logging, log_exception, log_info
from models.domain.copilot import CopilotSession
from models.domain.worker import WorkerStatus
from service.pipeline_service import PipelineService

_POLL_SECONDS = 2
_HEARTBEAT_SECONDS = 3
"""Well under the worker keyspace TTL (10 s)."""
_REAP_SECONDS = 30
"""How often a worker looks for the jobs of dead workers."""


class _Heartbeat:
    """Beats from a daemon thread until stopped; says what each lane is doing.
    The lanes update it from their threads: changes go under a lock."""

    def __init__(self, pipelines: PipelineService):
        now = datetime.now(timezone.utc)
        host, pid = socket.gethostname(), os.getpid()
        self.status = WorkerStatus(worker_id=f"{host}-{pid}", host=host, pid=pid, started_at=now, last_seen=now)
        self._pipelines = pipelines
        self._stop = threading.Event()
        self._lock = threading.Lock()

    def run(self, run_id: int | None) -> None:
        """The pipeline run in progress (None = the automation lane waits)."""
        with self._lock:
            self.status.busy_run_id = run_id
        self._beat()

    def copilot(self, session_id: int, busy: bool) -> None:
        """A Copilot session taken (``busy``) or let go by one of the Copilot lanes."""
        with self._lock:
            ids = [item for item in self.status.busy_copilot_session_ids if item != session_id]
            self.status.busy_copilot_session_ids = sorted([*ids, session_id]) if busy else ids
        self._beat()

    def start(self) -> None:
        self._beat()
        threading.Thread(target=self._loop, name="worker-heartbeat", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        self._pipelines.worker_stopped(self.status.worker_id)

    def _loop(self) -> None:
        while not self._stop.wait(_HEARTBEAT_SECONDS):
            self._beat()

    def _beat(self) -> None:
        if self._stop.is_set():
            return
        with self._lock:
            self.status.last_seen = datetime.now(timezone.utc)
            status = self.status.model_copy(deep=True)
        try:
            self._pipelines.heartbeat(status)
        except Exception:  # Redis hiccup: the next beat retries, the queue keeps going
            log_exception(LogPrefix.WORKER, "Heartbeat non inviato")


def _copilot_lane(name: str, claim: Callable[[], CopilotSession | None], run: Callable[[CopilotSession], object],
                  heartbeat: _Heartbeat) -> None:
    """Claim the lane's jobs and run each in its own thread; claims again at
    once after a job (there may be more), waits a little when there is none."""
    def work(session: CopilotSession, session_id: int) -> None:
        try:
            run(session)
        except Exception:  # e.g. the session was deleted meanwhile: the lane goes on
            log_exception(LogPrefix.WORKER, "Copilot (%s) non completato: sessione %s", name, session_id)
        finally:
            heartbeat.copilot(session_id, busy=False)

    while True:
        try:
            session = claim()
        except Exception:  # e.g. the DB is down for a moment
            log_exception(LogPrefix.WORKER, "Coda di Copilot (%s) non letta", name)
            session = None
        if session is None:
            time.sleep(_POLL_SECONDS)
            continue
        session_id = session.id or 0  # a claimed session is saved: it has one
        heartbeat.copilot(session_id, busy=True)
        threading.Thread(target=work, args=(session, session_id), name=f"copilot-{name}-{session_id}", daemon=True).start()


class _Reapable(Protocol):
    def fail_orphaned(self, alive_workers: set[str]) -> int: ...


def _reap(queues: Sequence[_Reapable], pipelines: PipelineService, me: str) -> int:
    """Fail the ``running`` jobs of the workers that stopped beating; how many.
    The workers come from Redis (``me`` always counts as alive): when it cannot
    be read nothing is failed, a live worker's job must never be."""
    try:
        alive = {worker.worker_id for worker in pipelines.workers()} | {me}
    except Exception:  # Redis down: try again next time
        log_exception(LogPrefix.WORKER, "Worker attivi non letti: controllo dei lavori interrotti rimandato")
        return 0
    failed = 0
    for queue in queues:
        try:
            failed += queue.fail_orphaned(alive)
        except Exception:  # e.g. the DB is down for a moment
            log_exception(LogPrefix.WORKER, "Lavori interrotti non controllati")
    if failed:
        log_info(LogPrefix.WORKER, "%s lavori di worker fermati segnati come interrotti", failed)
    return failed


def _reaper_lane(queues: Sequence[_Reapable], pipelines: PipelineService, me: str) -> None:
    while True:
        time.sleep(_REAP_SECONDS)
        _reap(queues, pipelines, me)


def main() -> None:
    configure_logging(Config.get().app_log_level)
    container = Container()
    runner = container.pipeline_runner
    copilot = container.copilot_service
    heartbeat = _Heartbeat(container.pipeline_service)
    me = heartbeat.status.worker_id
    heartbeat.start()  # beating before any claim: the others see this worker's jobs as alive
    queues = (runner, copilot)
    _reap(queues, container.pipeline_service, me)
    threading.Thread(target=_reaper_lane, args=(queues, container.pipeline_service, me), name="worker-reaper", daemon=True).start()
    for name, claim, run in (("esecuzioni", lambda: copilot.claim_execution(me), copilot.execute),
                             ("chat", lambda: copilot.claim_planning_turn(me), copilot.answer)):
        threading.Thread(target=_copilot_lane, args=(name, claim, run, heartbeat), name=f"copilot-{name}", daemon=True).start()
    log_info(LogPrefix.WORKER, "Worker %s in attesa di automation e lavori di Copilot (Ctrl+C per fermare)",
             heartbeat.status.worker_id)
    try:
        while True:  # the automation lane
            try:
                done = runner.run_next(on_claim=lambda claimed: heartbeat.run(claimed.id), worker_id=me)
                if done is None:
                    time.sleep(_POLL_SECONDS)
                else:
                    heartbeat.run(None)
            except Exception:  # e.g. the run was deleted while running: keep serving the queue
                log_exception(LogPrefix.WORKER, "Esecuzione non completata")
                heartbeat.run(None)
                time.sleep(_POLL_SECONDS)
    except KeyboardInterrupt:
        log_info(LogPrefix.WORKER, "Fermato")
    finally:
        heartbeat.stop()


if __name__ == "__main__":
    main()
