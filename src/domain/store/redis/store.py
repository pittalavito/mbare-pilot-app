"""Redis store facade: one import point for the Redis persistence layer.

Re-exports the Redis repositories and holds the translation seams:
``Factory`` (domain models -> Redis records, writes) and ``Adapter``
(Redis records -> domain models, reads).
"""
from domain.store.redis.repository import Client
from domain.store.redis.trace_repository import RedisTraceRepository
from models.domain.agent import AgentRunRecord
from models.store.redis import AgentTraceRecord

__all__ = ["Client", "RedisTraceRepository", "Factory"]


class Factory:
    """Write seam: domain models -> Redis records."""

    @staticmethod
    def to_trace_record(record: AgentRunRecord) -> AgentTraceRecord:
        return AgentTraceRecord(
            run_id=record.run_id,
            input=record.input,
            output=record.output,
            tool_calls=record.telemetry.tool_calls,
            generations=record.telemetry.generations,
        )
