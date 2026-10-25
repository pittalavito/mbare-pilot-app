"""Response models of the processes (/admin/worker, /admin/logs/{process})."""
from pydantic import BaseModel

from models.controller.pipeline import WorkerResponse
from models.domain.process import WorkerState


class WorkerStateResponse(BaseModel):
    status: str
    """``running`` (started by the app) | ``external`` (heartbeat only) | ``stopped``."""
    pid: int | None
    workers: list[WorkerResponse]

    @classmethod
    def from_state(cls, state: WorkerState) -> "WorkerStateResponse":
        return cls(status=state.status.value, pid=state.pid,
                   workers=[WorkerResponse.from_status(worker) for worker in state.workers])


class LogResponse(BaseModel):
    process: str
    text: str
    """The last lines of its log ('' when it has none)."""
