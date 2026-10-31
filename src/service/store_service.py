"""Single persistence facade for the app.

Builds and composes every repository behind one service-layer object: the DB
repositories (run facts), the Redis repositories (verbatim traces, cache, ...)
and the local file store, all from ``Config.get()``. The repositories deal only
in rows/records; the per-store ``Adapter``/``Factory`` translate to and from the
domain models.
"""
from pathlib import Path

import redis
from sqlalchemy.engine import Engine as SqlAlchemyEngine

from config import Config
from domain.store.db.repository import Engine
from domain.store.files.store import LocalFileRepository, StoredFile
from domain.store.redis.repository import Client as RedisClient


class StoreService:

    def __init__(self, engine: SqlAlchemyEngine | None = None, redis_client: redis.Redis | None = None):
        """Connects to Postgres and Redis from the Config; tests pass their own
        ``engine`` (in-memory SQLite) and ``redis_client`` (fakeredis)."""
        config = Config.get()
        if engine is None:
            engine = Engine.create_db_engine(config.database_url)
        self._engine = engine
        if redis_client is None:
            redis_client = RedisClient.create_redis_client(config.redis_url)

        self._files_repository = LocalFileRepository(config.project_data_root)
        self._definitions_repository = LocalFileRepository(config.definitions_root)

    # ----------------------------------------------------------------- files
    def list_files(self, prefix: str = "") -> list[StoredFile]:
        return self._files_repository.list(prefix)

    def save_file(self, file_id: str, data: bytes) -> StoredFile:
        return self._files_repository.save(file_id, data)

    def get_file(self, file_id: str) -> StoredFile | None:
        return self._files_repository.get(file_id)

    def read_file(self, file_id: str) -> bytes:
        return self._files_repository.read(file_id)

    def delete_file(self, file_id: str) -> bool:
        return self._files_repository.delete(file_id)

    def file_path(self, file_id: str) -> Path:
        """Where ``file_id`` is on disk: for a program that reads it itself (Copilot's --add-dir)."""
        return self._files_repository.path(file_id)

    def delete_folder(self, prefix: str) -> bool:
        """A folder of the file store with everything in it."""
        return self._files_repository.delete_tree(prefix)

    # ----------------------------------------------------------- definitions
    def read_definition(self, path: str) -> str | None:
        """A file under ``<data_home>/definition`` (e.g. ``project/acme/agent.yml``); None when missing."""
        if self._definitions_repository.get(path) is None:
            return None
        return self._definitions_repository.read(path).decode("utf-8")

    def list_definitions(self, folder: str) -> list[str]:
        """The files directly in ``<data_home>/definition/<folder>``, as paths relative to ``definition/``."""
        prefix = folder.strip("/")
        return [stored.file_id for stored in self._definitions_repository.list(prefix)
                if stored.file_id.rsplit("/", 1)[0] == prefix]

    def save_definition(self, path: str, text: str) -> None:
        self._definitions_repository.save(path, text.encode("utf-8"))
