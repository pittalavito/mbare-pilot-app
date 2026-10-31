"""The agents' runs: the facts (tokens, costs, latency, tool calls) in SQL, to
be queried and summed, and the verbatim trace (input, output, LLM
generations) in Redis, by the same ``run_id``."""
import redis
from sqlalchemy.engine import Engine

from domain.store.db.run_mapper import Adapter, Factory
from domain.store.db.run_repository import DbRunRepository
from domain.store.redis.trace_mapper import Factory as TraceFactory
from domain.store.redis.trace_repository import RedisTraceRepository
from models.domain.agent import AgentRunRecord, AgentRunSummary, ToolCallSummary
from models.store.redis import AgentTraceRecord


class RunStore:

    def __init__(self, engine: Engine, redis_client: redis.Redis):
        self._runs = DbRunRepository(engine)
        self._traces = RedisTraceRepository(redis_client)

    def save(self, record: AgentRunRecord) -> None:
        """Facts in SQL, verbatim trace in Redis (same run_id)."""
        self._runs.save_rows(Factory.to_run_row(record), Factory.to_tool_rows(record))
        self._traces.save(TraceFactory.to_trace_record(record))

    def list_runs(self, limit: int = 100) -> list[AgentRunSummary]:
        """Newest first."""
        return [Adapter.to_run_summary(row) for row in self._runs.list_recent(limit)]

    def list_tool_calls(self, limit: int = 100) -> list[ToolCallSummary]:
        """Newest first."""
        return [Adapter.to_tool_call_summary(row) for row in self._runs.list_recent_tool_calls(limit)]

    def get_trace(self, run_id: str) -> AgentTraceRecord | None:
        """None when missing or expired."""
        return self._traces.load(run_id)
