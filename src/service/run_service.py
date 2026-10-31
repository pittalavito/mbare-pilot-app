"""Observability of the agents' runs (Admin → Osservabilità): what ran, with
which tokens and costs, and the verbatim trace of one run. Read-only: the runs
are written by AgentService as they end."""
from core.error import NotFoundError
from models.domain.agent import AgentRunSummary, ToolCallSummary
from models.store.redis import AgentTraceRecord
from service.store.run_store import RunStore


class RunService:

    def __init__(self, runs: RunStore):
        self._runs = runs

    def list_runs(self, limit: int = 100) -> list[AgentRunSummary]:
        """Newest first."""
        return self._runs.list_runs(limit)

    def list_tool_calls(self, limit: int = 100) -> list[ToolCallSummary]:
        """Newest first."""
        return self._runs.list_tool_calls(limit)

    def trace(self, run_id: str) -> AgentTraceRecord:
        """Input, output, tool calls and LLM generations, as recorded."""
        trace = self._runs.get_trace(run_id)
        if trace is None:
            raise NotFoundError(f"Trace non trovato: {run_id}")
        return trace
