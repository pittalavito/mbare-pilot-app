"""Automation worker status: each running worker reports itself every few
seconds (heartbeat); a worker that stops reporting is gone."""
from datetime import datetime

from pydantic import BaseModel


class WorkerStatus(BaseModel):
    worker_id: str
    """``<host>-<pid>``: unique among the running workers."""
    host: str
    pid: int
    started_at: datetime
    last_seen: datetime
    busy_run_id: int | None = None
    """The pipeline run being executed; None = waiting for the queue."""
