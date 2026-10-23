"""Automation worker: a process apart from the API that executes the queued
pipeline runs, one at a time. Started from the UI's Backend panel (or `python src/worker.py`);
more workers can run together (the queue never hands a run to two of them).

While alive it beats every few seconds in Redis (also during a long run, from
a background thread), so the API knows which workers are running and what
they are doing; a worker that dies stops beating and disappears.

    python src/worker.py
"""
import os
import socket
import threading
import time
from datetime import datetime, timezone

from config import Config
from core.container import Container
from core.observability import LogPrefix, configure_logging, log_exception, log_info
from models.domain.worker import WorkerStatus
from service.pipeline_service import PipelineService

_POLL_SECONDS = 2
_HEARTBEAT_SECONDS = 3
"""Well under the worker keyspace TTL (10 s)."""


class _Heartbeat:
    """Beats from a daemon thread until stopped; ``busy`` is the run in progress."""

    def __init__(self, pipelines: PipelineService):
        now = datetime.now(timezone.utc)
        host, pid = socket.gethostname(), os.getpid()
        self.status = WorkerStatus(worker_id=f"{host}-{pid}", host=host, pid=pid, started_at=now, last_seen=now)
        self._pipelines = pipelines
        self._stop = threading.Event()

    def busy(self, run_id: int | None) -> None:
        self.status.busy_run_id = run_id
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
        self.status.last_seen = datetime.now(timezone.utc)
        try:
            self._pipelines.heartbeat(self.status)
        except Exception:  # Redis hiccup: the next beat retries, the queue keeps going
            log_exception(LogPrefix.WORKER, "Heartbeat non inviato")


def main() -> None:
    configure_logging(Config.get().app_log_level)
    container = Container()
    runner = container.pipeline_runner
    heartbeat = _Heartbeat(container.pipeline_service)
    interrupted = runner.fail_interrupted()
    if interrupted:
        log_info(LogPrefix.WORKER, "%s esecuzioni interrotte segnate come fallite", interrupted)
    heartbeat.start()
    log_info(LogPrefix.WORKER, "Worker %s in attesa di automation da eseguire (Ctrl+C per fermare)",
             heartbeat.status.worker_id)
    try:
        while True:
            try:
                run = runner.run_next(on_claim=lambda claimed: heartbeat.busy(claimed.id))
                if run is None:
                    time.sleep(_POLL_SECONDS)
                else:
                    heartbeat.busy(None)
            except Exception:  # e.g. the run was deleted while running: keep serving the queue
                log_exception(LogPrefix.WORKER, "Esecuzione non completata")
                heartbeat.busy(None)
                time.sleep(_POLL_SECONDS)
    except KeyboardInterrupt:
        log_info(LogPrefix.WORKER, "Fermato")
    finally:
        heartbeat.stop()


if __name__ == "__main__":
    main()
