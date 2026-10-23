"""Redis store facade: one import point for the Redis persistence layer.

Re-exports the Redis repositories and holds the translation seams:
``Factory`` (domain models -> Redis records, writes) and ``Adapter``
(Redis records -> domain models, reads).
"""
from domain.store.redis.mask_repository import RedisMaskRepository
from domain.store.redis.repository import Client
from domain.store.redis.trace_repository import RedisTraceRepository
from domain.store.redis.worker_repository import RedisWorkerRepository
from models.domain.agent import AgentRunRecord
from models.domain.masking import MaskCategory, MaskEntry
from models.domain.worker import WorkerStatus
from models.store.redis import AgentTraceRecord, MaskRecord, WorkerHeartbeatRecord

__all__ = ["Client", "RedisMaskRepository", "RedisTraceRepository", "RedisWorkerRepository", "Factory", "Adapter"]


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

    @staticmethod
    def to_heartbeat_record(status: WorkerStatus) -> WorkerHeartbeatRecord:
        return WorkerHeartbeatRecord(**status.model_dump())


class Adapter:
    """Read seam: Redis records -> domain models."""

    @staticmethod
    def to_worker_status(record: WorkerHeartbeatRecord) -> WorkerStatus:
        return WorkerStatus(**record.model_dump())

    @staticmethod
    def to_mask_entry(record: MaskRecord) -> MaskEntry:
        return MaskEntry(category=MaskCategory(record.category), value=record.value, alias=record.alias,
                         manual=record.manual)
