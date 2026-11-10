"""The Metriche page's response (/observability/metrics)."""
from pydantic import BaseModel

from models.controller.copilot import CopilotModelUsageResponse
from models.domain.evaluation import EvaluationKind, EvaluationReport, EvaluationRun
from models.domain.metrics import AgentMetrics, Metrics, WipMetrics


class MetricsResponse(BaseModel):
    days: int | None
    project_name: str | None
    agents: list[AgentMetrics]
    copilot: list[CopilotModelUsageResponse]
    """In AI credits, not euros: apart from the agents."""
    wip: WipMetrics

    @classmethod
    def from_metrics(cls, metrics: Metrics) -> "MetricsResponse":
        return cls(days=metrics.days, project_name=metrics.project_name, agents=metrics.agents,
                   copilot=[CopilotModelUsageResponse.from_model_usage(item) for item in metrics.copilot], wip=metrics.wip)


class EvaluationRequest(BaseModel):
    kind: EvaluationKind
    models: list[str] = []
    """WIP: the catalog models to compare (at least one)."""
    embedders: list[str] = []
    """RAG: ``hashing`` and/or ``openrouter/<model>``; empty = ``hashing``."""


class EvaluationsResponse(BaseModel):
    runs: list[EvaluationRun]
    """The last ones launched from the page, newest first."""
    reports: list[EvaluationReport]
    """Every report on disk (from the page or the scripts), newest first."""
