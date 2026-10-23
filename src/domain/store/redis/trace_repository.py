"""Verbatim agent traces (keyspace agent-trace), one record per run."""
import redis

from domain.store.redis.repository import AGENT_TRACE_KEYSPACE, RedisRepository
from models.store.redis import AgentTraceRecord


class RedisTraceRepository(RedisRepository):

    def __init__(self, client: redis.Redis):
        super().__init__(client, AGENT_TRACE_KEYSPACE)

    def save(self, record: AgentTraceRecord) -> None:
        """Persist the run's trace; saving an existing run_id replaces it."""
        self._set(record.run_id, record.model_dump_json())

    def load(self, run_id: str) -> AgentTraceRecord | None:
        return self._load(run_id, AgentTraceRecord)

    def delete(self, run_id: str) -> None:
        self._delete(run_id)
