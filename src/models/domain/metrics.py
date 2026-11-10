"""The numbers of the Metriche page (service/metrics_service.py): cost and
latency of every agent, chatbot and «Elabora WIP», Copilot's usage apart (it
is billed in AI credits, not euros), and how the WIP proposals were received."""
from pydantic import BaseModel, Field

from models.domain.copilot import CopilotModelUsage


class AgentMetrics(BaseModel):
    """One agent, chatbot or «Elabora WIP» (``name`` = the run's config_name) over the period."""
    name: str
    calls: int
    errors: int
    input_tokens: int
    output_tokens: int
    cost_eur: float
    latency_avg_ms: float
    latency_p95_ms: float
    """95% of the calls took this long or less."""
    models: list[str] = Field(default_factory=list)


class WipMetrics(BaseModel):
    """How the «Elabora WIP» proposals were received over the period."""
    runs: int
    """Calls that gave proposals."""
    applied: int
    dismissed: int
    """Closed without applying any («Annulla»)."""
    open: int
    """Neither applied nor dismissed (the window was left)."""
    proposed: int
    accepted: int
    corrected: int
    discarded: int
    skipped: int
    acceptance_rate: float | None = None
    """Accepted as proposed over the proposals decided (applied or dismissed runs); None without any."""


class Metrics(BaseModel):
    days: int | None
    """The period: the last ``days`` days, None = ever."""
    project_name: str | None
    agents: list[AgentMetrics]
    """The most expensive first."""
    copilot: list[CopilotModelUsage]
    wip: WipMetrics
