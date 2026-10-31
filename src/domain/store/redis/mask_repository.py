"""Masking maps of the projects (keyspace mask), permanent. Per project:

- ``<project>:entries``: hash alias → MaskRecord as JSON;
- ``<project>:index``: hash lowercased value → alias (one alias per value);
- ``<project>:counter:<category>``: last number used for that category, so
  aliases are never reused, even after a removal.
"""
from typing import cast

import redis

from domain.store.redis.repository import MASK_KEYSPACE, RedisRepository
from models.store.redis import MaskRecord


class RedisMaskRepository(RedisRepository):

    def __init__(self, client: redis.Redis):
        super().__init__(client, MASK_KEYSPACE)

    def list(self, project_name: str) -> list[MaskRecord]:
        raw = self._client.hvals(self._key(project_name, "entries"))
        return [MaskRecord.model_validate_json(item) for item in raw]

    def find(self, project_name: str, value: str) -> MaskRecord | None:
        alias = cast(str | None, self._client.hget(self._key(project_name, "index"), value.lower()))  # decode_responses=True
        return self.get(project_name, alias) if alias else None

    def get(self, project_name: str, alias: str) -> MaskRecord | None:
        raw = self._client.hget(self._key(project_name, "entries"), alias)
        return MaskRecord.model_validate_json(raw) if raw else None

    def add(self, project_name: str, category: str, prefix: str, value: str, manual: bool) -> MaskRecord:
        """The entry of ``value``: the existing one, or a new one with the next
        alias of its category (``<prefix>_<n>``)."""
        existing = self.find(project_name, value)
        if existing is not None:
            return existing
        number = self._client.incr(self._key(project_name, f"counter:{category}"))
        record = MaskRecord(category=category, value=value, alias=f"{prefix}_{number}", manual=manual)
        if not self._client.hsetnx(self._key(project_name, "index"), value.lower(), record.alias):
            return self.find(project_name, value) or record  # registered meanwhile by another run
        self._client.hset(self._key(project_name, "entries"), record.alias, record.model_dump_json())
        return record

    def delete(self, project_name: str, alias: str) -> bool:
        record = self.get(project_name, alias)
        if record is None:
            return False
        self._client.hdel(self._key(project_name, "entries"), alias)
        self._client.hdel(self._key(project_name, "index"), record.value.lower())
        return True

    def delete_project(self, project_name: str) -> None:
        """The whole map, counters included."""
        keys = list(self._client.scan_iter(f"{self._key(project_name, '')}*"))
        if keys:
            self._client.delete(*keys)

    def _key(self, project_name: str, part: str) -> str:
        return self._keyspace.key(f"{project_name}:{part}")
