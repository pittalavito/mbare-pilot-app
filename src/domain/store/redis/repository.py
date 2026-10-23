"""Redis persistence base for the Redis store: the ``RedisKeyspace`` registry
(keyspace definitions), the ``Client`` (connect + ping, fail-fast) and the
``RedisRepository`` base every concrete repository extends. Concrete
repositories live in their own files under domain/store/redis/.

Each keyspace is a flat namespace ``<namespace>:<name>:<suffix>``, so the
Redis "schema" lives in one place: add a keyspace here (e.g. cache with a
TTL, RAG index, chat sessions) when a feature needs it.
"""
from dataclasses import dataclass
from typing import TypeVar

import redis
from pydantic import BaseModel

from core.observability import LogPrefix, log_warning

_NAMESPACE = "app"

_T = TypeVar("_T", bound=BaseModel)


@dataclass(frozen=True)
class RedisKeyspace:
    """One Redis keyspace: a key prefix plus a description of its value.
    ``default_ttl_seconds`` <= 0 means keys are permanent."""

    name: str
    value: str
    default_ttl_seconds: int = 0

    @property
    def prefix(self) -> str:
        """Key prefix, e.g. ``app:agent-trace:``."""
        return f"{_NAMESPACE}:{self.name}:"

    def key(self, suffix: str) -> str:
        """Full Redis key for a given id/suffix."""
        return f"{self.prefix}{suffix}"


AGENT_TRACE_KEYSPACE = RedisKeyspace(
    name="agent-trace",
    value="models.store.redis.AgentTraceRecord as JSON. Suffix = run_id.",
)

WORKER_KEYSPACE = RedisKeyspace(
    name="worker",
    value="models.store.redis.WorkerHeartbeatRecord as JSON. Suffix = worker_id. Expires when the worker stops beating.",
    default_ttl_seconds=10,
)


class Client:
    """Centralized Redis client creation. Redis is a hard dependency: an
    unreachable server is a startup error, never a silent degradation."""

    @staticmethod
    def create_redis_client(redis_url: str) -> redis.Redis:
        """Connect to Redis and verify it responds. Raises RuntimeError on failure."""
        try:
            client = redis.Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=2,
            )
            client.ping()
        except redis.RedisError as exc:
            raise RuntimeError(f"Redis unreachable at {redis_url}.") from exc
        return client


class RedisRepository:
    """Common plumbing: keyspace-prefixed keys and TTL-aware writes. The TTL
    defaults to the keyspace's own (<= 0 = permanent)."""

    def __init__(self, client: redis.Redis, keyspace: RedisKeyspace, ttl_seconds: int | None = None):
        self._client = client
        self._keyspace = keyspace
        self._ttl = keyspace.default_ttl_seconds if ttl_seconds is None else ttl_seconds

    def _get(self, suffix: str) -> str | None:
        """Raw value under this keyspace, or None if absent."""
        return self._client.get(self._keyspace.key(suffix))

    def _load(self, suffix: str, model_cls: type[_T]) -> _T | None:
        """Read + validate one typed value: None if absent, and None with a
        warning if the stored JSON is malformed."""
        raw = self._get(suffix)
        if raw is None:
            return None
        try:
            return model_cls.model_validate_json(raw)
        except ValueError:
            log_warning(LogPrefix.REDIS_MALFORMED_DATA, "Discarding malformed %s: %s", model_cls.__name__, self._keyspace.key(suffix))
            return None

    def _set(self, suffix: str, value: str) -> None:
        """Write under this keyspace, applying the configured TTL."""
        key = self._keyspace.key(suffix)
        if self._ttl > 0:
            self._client.set(key, value, ex=self._ttl)
        else:
            self._client.set(key, value)

    def _delete(self, suffix: str) -> None:
        """Remove one key from this keyspace (absent key = no-op)."""
        self._client.delete(self._keyspace.key(suffix))
