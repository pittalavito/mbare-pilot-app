"""Automation endpoints: a project's pipelines (/projects/{project}/pipelines,
/pipelines/{id}), their runs (queued here, executed by the worker), the
running workers (/workers) and the functions a FUNCTION step can call (/functions)."""
from fastapi import APIRouter, Depends, Response, status

from controller.dependencies import pipeline_service
from core.error import NotFoundError
from models.controller.pipeline import FunctionResponse, PipelineRequest, PipelineResponse, RunRequest, RunResponse, WorkerResponse
from service.pipeline_service import PipelineService

router = APIRouter(tags=["automation"])


@router.get("/projects/{project}/pipelines")
def list_pipelines(project: str, service: PipelineService = Depends(pipeline_service)) -> list[PipelineResponse]:
    return [PipelineResponse.from_pipeline(pipeline) for pipeline in service.list_pipelines(project)]


@router.post("/projects/{project}/pipelines", status_code=status.HTTP_201_CREATED)
def create_pipeline(project: str, request: PipelineRequest, service: PipelineService = Depends(pipeline_service)) -> PipelineResponse:
    pipeline = service.create_pipeline(
        project, 
        request.name, 
        description=request.description, 
        active=request.active,
        steps=[step.to_step() for step in request.steps], 
        edges=[edge.to_edge() for edge in request.edges],
    )
    return PipelineResponse.from_pipeline(pipeline)


@router.put("/pipelines/{pipeline_id}")
def update_pipeline(pipeline_id: int, request: PipelineRequest, service: PipelineService = Depends(pipeline_service)) -> PipelineResponse:
    pipeline = service.update_pipeline(
        pipeline_id, 
        name=request.name, 
        description=request.description, 
        active=request.active,
        steps=[step.to_step() for step in request.steps], 
        edges=[edge.to_edge() for edge in request.edges],
    )
    return PipelineResponse.from_pipeline(pipeline)


@router.delete("/pipelines/{pipeline_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pipeline(pipeline_id: int, service: PipelineService = Depends(pipeline_service)) -> Response:
    """With its run history; the agent runs stay in Observability."""
    if not service.delete_pipeline(pipeline_id):
        raise NotFoundError(f"Automation non trovata: {pipeline_id}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------- runs

@router.get("/pipelines/{pipeline_id}/runs")
def list_runs(pipeline_id: int, limit: int = 20, service: PipelineService = Depends(pipeline_service)) -> list[RunResponse]:
    """Newest first, with their steps."""
    return [RunResponse.from_run(run) for run in service.list_runs(pipeline_id, limit)]


@router.post("/pipelines/{pipeline_id}/runs", status_code=status.HTTP_201_CREATED)
def enqueue_run(pipeline_id: int, request: RunRequest, service: PipelineService = Depends(pipeline_service)) -> RunResponse:
    """Queue a run: the worker executes it."""
    return RunResponse.from_run(service.enqueue(pipeline_id, request.input))


@router.delete("/pipeline-runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_run(run_id: int, service: PipelineService = Depends(pipeline_service)) -> Response:
    """Not while running (400)."""
    service.delete_run(run_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/functions")
def list_functions(service: PipelineService = Depends(pipeline_service)) -> list[FunctionResponse]:
    return [FunctionResponse.from_spec(spec) for spec in service.available_functions()]


@router.get("/workers")
def list_workers(service: PipelineService = Depends(pipeline_service)) -> list[WorkerResponse]:
    """The running workers (heartbeat in the last few seconds)."""
    return [WorkerResponse.from_status(worker) for worker in service.workers()]


@router.get("/workers/health")
def workers_health(service: PipelineService = Depends(pipeline_service)) -> Response:
    """200 when at least one worker is running, 503 otherwise (for monitoring)."""
    alive = bool(service.workers())
    return Response(status_code=status.HTTP_200_OK if alive else status.HTTP_503_SERVICE_UNAVAILABLE)
