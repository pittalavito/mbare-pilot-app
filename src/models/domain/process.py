"""The app's background processes as the API sees them: the worker (started
and stopped by the API, or elsewhere) and the logs of the API and the worker."""
from enum import StrEnum

from pydantic import BaseModel, Field

from models.domain.worker import WorkerStatus


class ProcessName(StrEnum):
    """Processes with a log in ``resource/logs/<name>.log``."""
    API = "api"
    WORKER = "worker"


class WorkerProcessStatus(StrEnum):
    RUNNING = "running"
    """Started by the app (PID file)."""
    EXTERNAL = "external"
    """Not started by the app, but a worker sends its heartbeat (e.g. from a terminal)."""
    STOPPED = "stopped"


class WorkerState(BaseModel):
    status: WorkerProcessStatus
    pid: int | None = None
    """Of the process started by the app; None otherwise."""
    workers: list[WorkerStatus] = Field(default_factory=list)
    """The workers sending their heartbeat (busy or waiting), wherever they were started."""
