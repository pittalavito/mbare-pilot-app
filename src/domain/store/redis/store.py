"""Redis store facade: one import point for the Redis persistence layer.

Re-exports the Redis repositories and holds the translation seams:
``Factory`` (domain models -> Redis records, writes) and ``Adapter``
(Redis records -> domain models, reads).
"""
from domain.store.redis.mask_repository import RedisMaskRepository
from domain.store.redis.repository import Client
from domain.store.redis.trace_repository import RedisTraceRepository
from models.domain.agent import AgentRunRecord
from models.domain.masking import MaskCategory, MaskEntry
from models.store.redis import AgentTraceRecord, MaskRecord

__all__ = ["Client", "RedisMaskRepository", "RedisTraceRepository", "Factory", "Adapter"]


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


class Adapter:
    """Read seam: Redis records -> domain models."""

    @staticmethod
    def to_mask_entry(record: MaskRecord) -> MaskEntry:
        return MaskEntry(category=MaskCategory(record.category), value=record.value, alias=record.alias,
                         manual=record.manual)
