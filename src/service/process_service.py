"""The worker as a process the API starts and stops (the frontend cannot start
processes), and the logs of the API and the worker. A worker started elsewhere
(a terminal, the Streamlit UI's own manager) is seen through its heartbeat."""
from core.error import ConflictError
from core.observability import LogPrefix, observed
from domain.process.manager import ProcessManager
from models.domain.process import ProcessName, WorkerProcessStatus, WorkerState
from service.pipeline_service import PipelineService


class ProcessService:

    def __init__(self, pipeline_service: PipelineService, manager: ProcessManager, worker_command: list[str]):
        self._pipelines = pipeline_service
        self._manager = manager
        self._worker_command = worker_command

    def worker(self) -> WorkerState:
        pid = self._manager.pid(ProcessName.WORKER)
        heartbeats = self._pipelines.workers()
        if pid is not None:
            status = WorkerProcessStatus.RUNNING
        else:
            status = WorkerProcessStatus.EXTERNAL if heartbeats else WorkerProcessStatus.STOPPED
        return WorkerState(status=status, pid=pid, workers=heartbeats)

    @observed(LogPrefix.PROCESS_SERVICE)
    def start_worker(self) -> WorkerState:
        """No-op when already started here; refused when one runs elsewhere."""
        if self.worker().status is WorkerProcessStatus.EXTERNAL:
            raise ConflictError("Il worker è già attivo, avviato fuori dall'app: fermalo da lì.")
        self._manager.start(ProcessName.WORKER, self._worker_command)
        return self.worker()

    @observed(LogPrefix.PROCESS_SERVICE)
    def stop_worker(self) -> WorkerState:
        """Only a worker started here (one started elsewhere is stopped from there)."""
        self._manager.stop(ProcessName.WORKER)
        return self.worker()

    def logs(self, name: ProcessName, lines: int = 200) -> str:
        return self._manager.logs(name, lines)
