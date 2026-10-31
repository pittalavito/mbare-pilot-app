"""Worker heartbeats: domain ``WorkerStatus`` <-> Redis ``WorkerHeartbeatRecord``."""
from models.domain.worker import WorkerStatus
from models.store.redis import WorkerHeartbeatRecord


class Factory:
    """Write seam: domain models -> Redis records."""

    @staticmethod
    def to_heartbeat_record(status: WorkerStatus) -> WorkerHeartbeatRecord:
        return WorkerHeartbeatRecord(**status.model_dump())


class Adapter:
    """Read seam: Redis records -> domain models."""

    @staticmethod
    def to_worker_status(record: WorkerHeartbeatRecord) -> WorkerStatus:
        return WorkerStatus(**record.model_dump())
