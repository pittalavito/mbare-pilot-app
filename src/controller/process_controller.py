"""The background processes: the worker started and stopped by the API
(/admin/worker) and the logs of the API and the worker (/admin/logs/{process})."""
from fastapi import APIRouter, Depends, Query

from controller.dependencies import process_service
from models.controller.process import LogResponse, WorkerStateResponse
from models.domain.process import ProcessName
from service.process_service import ProcessService

router = APIRouter(prefix="/admin", tags=["processes"])


@router.get("/worker")
def worker(service: ProcessService = Depends(process_service)) -> WorkerStateResponse:
    return WorkerStateResponse.from_state(service.worker())


@router.post("/worker/start")
def start_worker(service: ProcessService = Depends(process_service)) -> WorkerStateResponse:
    """409 when a worker started elsewhere is running."""
    return WorkerStateResponse.from_state(service.start_worker())


@router.post("/worker/stop")
def stop_worker(service: ProcessService = Depends(process_service)) -> WorkerStateResponse:
    return WorkerStateResponse.from_state(service.stop_worker())


@router.get("/logs/{process}")
def logs(process: ProcessName, lines: int = Query(200, ge=1, le=5000),
         service: ProcessService = Depends(process_service)) -> LogResponse:
    return LogResponse(process=process.value, text=service.logs(process, lines))
