"""Heartbeats of the running automation workers (keyspace worker): a key per
worker, rewritten every few seconds and expiring when the worker stops."""
import redis

from domain.store.redis.repository import WORKER_KEYSPACE, RedisRepository
from models.store.redis import WorkerHeartbeatRecord


class RedisWorkerRepository(RedisRepository):

    def __init__(self, client: redis.Redis):
        super().__init__(client, WORKER_KEYSPACE)

    def save(self, record: WorkerHeartbeatRecord) -> None:
        """Write the heartbeat, renewing its TTL."""
        self._set(record.worker_id, record.model_dump_json())

    def list_alive(self) -> list[WorkerHeartbeatRecord]:
        """The workers whose heartbeat has not expired yet."""
        suffixes = [key.removeprefix(WORKER_KEYSPACE.prefix) for key in self._client.scan_iter(f"{WORKER_KEYSPACE.prefix}*")]
        records = [self._load(suffix, WorkerHeartbeatRecord) for suffix in suffixes]
        return [record for record in records if record is not None]

    def delete(self, worker_id: str) -> None:
        self._delete(worker_id)
