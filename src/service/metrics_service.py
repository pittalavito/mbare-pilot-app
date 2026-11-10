"""The Metriche page (Admin → Observability): what the agents cost and how long
they take, grouped by who (the run's config_name: a chatbot, a Library agent,
``wip/<secretary>``...), Copilot's usage apart (AI credits, not euros), and
the acceptance of «Elabora WIP»'s proposals. Computed in Python over the
period's rows (average and p95 alike on Postgres and SQLite)."""
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from models.domain.agent import AgentRunSummary
from models.domain.metrics import AgentMetrics, Metrics, WipMetrics
from models.domain.wip import WipRun
from service.store.copilot_store import CopilotStore
from service.store.run_store import RunStore
from service.store.wip_store import WipStore


class MetricsService:

    def __init__(self, runs: RunStore, copilot: CopilotStore, wip_runs: WipStore):
        self._runs = runs
        self._copilot = copilot
        self._wip = wip_runs

    def metrics(self, days: int | None = None, project_name: str | None = None) -> Metrics:
        """The last ``days`` days (None = ever), of ``project_name`` (None = every project)."""
        since = datetime.now(timezone.utc) - timedelta(days=days) if days else None
        grouped: dict[str, list[AgentRunSummary]] = defaultdict(list)
        for run in self._runs.list_since(since, project_name):
            grouped[run.config_name].append(run)
        agents = sorted((_agent(name, runs) for name, runs in grouped.items()), key=lambda item: (-item.cost_eur, -item.calls, item.name))
        return Metrics(days=days, project_name=project_name, agents=agents, copilot=self._copilot.usage_by_model(since, project_name),
                       wip=_wip(self._wip.list_since(since, project_name)))


def percentile(values: list[float], share: float) -> float:
    """The ``share`` percentile (0..1) by the nearest-rank method; 0 for no values."""
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(math.ceil(share * len(ordered)) - 1, 0)]


def _agent(name: str, runs: list[AgentRunSummary]) -> AgentMetrics:
    latencies = [run.latency_ms for run in runs]
    return AgentMetrics(
        name=name, calls=len(runs), errors=sum(not run.ok for run in runs),
        input_tokens=sum(run.total_tokens.input_tokens for run in runs), output_tokens=sum(run.total_tokens.output_tokens for run in runs),
        cost_eur=round(sum(run.total_tokens.cost_eur for run in runs), 6), latency_avg_ms=round(sum(latencies) / len(latencies), 1),
        latency_p95_ms=round(percentile(latencies, 0.95), 1), models=sorted({run.model for run in runs}),
    )


def _wip(runs: list[WipRun]) -> WipMetrics:
    applied = [run for run in runs if run.applied_at is not None]
    dismissed = [run for run in runs if run.dismissed_at is not None]
    decided = applied + dismissed
    accepted = sum(run.accepted for run in applied)
    decided_proposals = sum(run.accepted + run.corrected + run.discarded + run.skipped for run in decided)
    return WipMetrics(
        runs=len(runs), applied=len(applied), dismissed=len(dismissed), open=len(runs) - len(decided), proposed=sum(run.proposed for run in runs),
        accepted=accepted, corrected=sum(run.corrected for run in applied), discarded=sum(run.discarded for run in decided),
        skipped=sum(run.skipped for run in applied),
        acceptance_rate=round(accepted / decided_proposals, 3) if decided_proposals else None,
    )
