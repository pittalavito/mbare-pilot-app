"""Redis store facade: one import point for the Redis persistence layer.

Re-exports the Redis repositories and holds the translation seams:
``Factory`` (domain models -> Redis records, writes) and ``Adapter``
(Redis records -> domain models, reads).
"""
from domain.store.redis.repository import Client
from domain.store.redis.trace_repository import RedisTraceRepository
from domain.store.redis.worker_repository import RedisWorkerRepository
from models.domain.agent import AgentRunRecord
from models.domain.worker import WorkerStatus
from models.store.redis import AgentTraceRecord, WorkerHeartbeatRecord

__all__ = ["Client", "RedisTraceRepository", "RedisWorkerRepository", "Factory", "Adapter"]


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
