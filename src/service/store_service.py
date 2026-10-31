"""Single persistence facade for the app.

Builds and composes every repository behind one service-layer object: the DB
repositories (run facts), the Redis repositories (verbatim traces, cache, ...)
and the local file store, all from ``Config.get()``. The repositories deal only
in rows/records; the per-store ``Adapter``/``Factory`` translate to and from the
domain models.
"""
from datetime import datetime
from pathlib import Path

import redis
from sqlalchemy.engine import Engine as SqlAlchemyEngine

from config import Config
from domain.store.db.store import (
    Adapter as DbAdapter,
    DbCopilotMessageRepository,
    DbCopilotSessionRepository,
    DbCopilotTurnRepository,
    Engine,
    Factory as DbFactory,
)
from domain.store.files.store import LocalFileRepository, StoredFile
from domain.store.redis.repository import Client as RedisClient
from models.domain.copilot import CopilotMessage, CopilotModelUsage, CopilotSession, CopilotSessionStatus, CopilotTurnRecord


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

        self._copilot_session_repository = DbCopilotSessionRepository(engine)
        self._copilot_message_repository = DbCopilotMessageRepository(engine)
        self._copilot_turn_repository = DbCopilotTurnRepository(engine)
        self._files_repository = LocalFileRepository(config.project_data_root)
        self._definitions_repository = LocalFileRepository(config.definitions_root)

    # --------------------------------------------------------------- copilot
    def save_copilot_session(self, session: CopilotSession) -> CopilotSession:
        """Insert (``id`` None) or update."""
        return DbAdapter.to_copilot_session(self._copilot_session_repository.save(DbFactory.to_copilot_session_row(session)))

    def update_copilot_session(self, session_id: int, **changes) -> CopilotSession:
        """Only ``changes`` (domain field names and values), not the whole row."""
        row = DbFactory.to_copilot_session_row(self.get_copilot_session(session_id).model_copy(update=changes))
        fields = {name: getattr(row, name) for name in changes}
        return DbAdapter.to_copilot_session(self._copilot_session_repository.update_fields(session_id, fields))

    def get_copilot_session(self, session_id: int) -> CopilotSession | None:
        row = self._copilot_session_repository.get(session_id)
        return DbAdapter.to_copilot_session(row) if row else None

    def list_copilot_sessions(self, project_name: str) -> list[CopilotSession]:
        """Newest first."""
        return [DbAdapter.to_copilot_session(row) for row in self._copilot_session_repository.list_for_project(project_name)]

    def list_copilot_sessions_by_status(self, status: CopilotSessionStatus) -> list[CopilotSession]:
        return [DbAdapter.to_copilot_session(row) for row in self._copilot_session_repository.list_by_status(status.value)]

    def claim_next_copilot_session(self) -> CopilotSession | None:
        """The next queued execution whose repository is free, now ``running``."""
        row = self._copilot_session_repository.claim_next()
        return DbAdapter.to_copilot_session(row) if row else None

    def delete_copilot_session(self, session_id: int) -> bool:
        """With its messages."""
        return self._copilot_session_repository.delete(session_id)

    def add_copilot_message(self, message: CopilotMessage) -> CopilotMessage:
        return DbAdapter.to_copilot_message(self._copilot_message_repository.save(DbFactory.to_copilot_message_row(message)))

    def list_copilot_messages(self, session_id: int) -> list[CopilotMessage]:
        """Oldest first."""
        return [DbAdapter.to_copilot_message(row) for row in self._copilot_message_repository.list_for_session(session_id)]

    def add_copilot_turn(self, turn: CopilotTurnRecord) -> CopilotTurnRecord:
        return DbAdapter.to_copilot_turn(self._copilot_turn_repository.save(DbFactory.to_copilot_turn_row(turn)))

    def list_copilot_turns(self, limit: int = 100, project_name: str | None = None) -> list[CopilotTurnRecord]:
        """Newest first."""
        return [DbAdapter.to_copilot_turn(row) for row in self._copilot_turn_repository.list_recent(limit, project_name)]

    def list_copilot_session_turns(self, session_id: int) -> list[CopilotTurnRecord]:
        """Oldest first."""
        return [DbAdapter.to_copilot_turn(row) for row in self._copilot_turn_repository.list_for_session(session_id)]

    def copilot_usage_by_model(self, since: datetime | None = None, project_name: str | None = None) -> list[CopilotModelUsage]:
        """The most AI credits first."""
        return [DbAdapter.to_copilot_model_usage(row) for row in self._copilot_turn_repository.totals_by_model(since, project_name)]

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
