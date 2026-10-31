"""Heartbeats of the automation workers (Redis, with a TTL): a worker that
stops writing disappears from the list by itself."""
import redis

from domain.store.redis.worker_mapper import Adapter, Factory
from domain.store.redis.worker_repository import RedisWorkerRepository
from models.domain.worker import WorkerStatus


class WorkerStore:

    def __init__(self, redis_client: redis.Redis):
        self._workers = RedisWorkerRepository(redis_client)

    def save_heartbeat(self, status: WorkerStatus) -> None:
        self._workers.save(Factory.to_heartbeat_record(status))

    def list_alive(self) -> list[WorkerStatus]:
        return [Adapter.to_worker_status(record) for record in self._workers.list_alive()]

    def delete(self, worker_id: str) -> None:
        self._workers.delete(worker_id)
