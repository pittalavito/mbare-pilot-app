"""The Metriche page (Admin → Observability → Metriche): cost and latency per
agent, Copilot's usage, the acceptance of «Elabora WIP», and the evaluations
(launched from here in the worker, or from resource/scripts)."""
from fastapi import APIRouter, Depends, status
from fastapi.responses import PlainTextResponse

from controller.dependencies import evaluation_service, metrics_service
from models.controller.metrics import EvaluationRequest, EvaluationsResponse, MetricsResponse
from models.domain.evaluation import EvaluationRun
from service.evaluation_service import EvaluationService
from service.metrics_service import MetricsService

router = APIRouter(prefix="/observability", tags=["metrics"])


@router.get("/metrics")
def metrics(days: int | None = None, project: str | None = None, service: MetricsService = Depends(metrics_service)) -> MetricsResponse:
    """The last ``days`` days (omitted = ever), of ``project`` (omitted = every project)."""
    return MetricsResponse.from_metrics(service.metrics(days, project))


@router.get("/evaluations")
def evaluations(service: EvaluationService = Depends(evaluation_service)) -> EvaluationsResponse:
    """The evaluations launched from the page and every report on disk."""
    return EvaluationsResponse(runs=service.runs(), reports=service.reports())


@router.post("/evaluations", status_code=status.HTTP_201_CREATED)
def launch_evaluation(request: EvaluationRequest, service: EvaluationService = Depends(evaluation_service)) -> EvaluationRun:
    """Queued for the worker (it may take minutes and it costs: real models)."""
    return service.enqueue(request.kind, request.models, request.embedders)


@router.get("/evaluations/reports/{name}", response_class=PlainTextResponse)
def evaluation_report(name: str, format: str = "md", service: EvaluationService = Depends(evaluation_service)) -> PlainTextResponse:
    """A report as markdown (``format=md``) or JSON (``format=json``)."""
    media = "application/json" if format == "json" else "text/markdown; charset=utf-8"
    return PlainTextResponse(service.report(name, format), media_type=media)
