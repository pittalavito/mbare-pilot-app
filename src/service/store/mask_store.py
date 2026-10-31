"""The projects' masking maps (Redis, permanent): sensitive value -> alias."""
import redis

from domain.store.redis.mask_mapper import Adapter
from domain.store.redis.mask_repository import RedisMaskRepository
from models.domain.masking import MaskCategory, MaskEntry


class MaskStore:

    def __init__(self, redis_client: redis.Redis):
        self._masks = RedisMaskRepository(redis_client)

    def list(self, project_name: str) -> list[MaskEntry]:
        """By category, then alias number (``EMAIL_2`` before ``EMAIL_10``)."""
        entries = [Adapter.to_mask_entry(record) for record in self._masks.list(project_name)]
        return sorted(entries, key=lambda entry: (entry.category.value, int(entry.alias.rsplit("_", 1)[1])))

    def add(self, project_name: str, category: MaskCategory, value: str, manual: bool) -> MaskEntry:
        record = self._masks.add(project_name, category.value, category.alias_prefix, value, manual)
        return Adapter.to_mask_entry(record)

    def delete(self, project_name: str, alias: str) -> bool:
        return self._masks.delete(project_name, alias)

    def delete_project(self, project_name: str) -> None:
        """The whole map of the project."""
        self._masks.delete_project(project_name)
