"""Automation worker status: each running worker reports itself every few
seconds (heartbeat); a worker that stops reporting is gone."""
from datetime import datetime

from pydantic import BaseModel, Field


class WorkerStatus(BaseModel):
    worker_id: str
    """``<host>-<pid>``: unique among the running workers."""
    host: str
    pid: int
    started_at: datetime
    last_seen: datetime
    busy_run_id: int | None = None
    """The pipeline run being executed; None = waiting for the queue."""
    busy_copilot_session_ids: list[int] = Field(default_factory=list)
    """The Copilot sessions it is working on (executions and planning turns, in parallel)."""
