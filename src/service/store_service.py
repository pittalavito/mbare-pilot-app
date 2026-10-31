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
from core.observability import LogPrefix, log_warning
from core.secret_box import SecretBox
from domain.store.db.store import (
    Adapter as DbAdapter,
    DbAtlassianFavoriteRepository,
    DbAtlassianRepository,
    DbAutomationCacheRepository,
    DbChatbotRepository,
    DbConversationRepository,
    DbCopilotMessageRepository,
    DbCopilotSessionRepository,
    DbCopilotTurnRepository,
    DbMessageRepository,
    DbPipelineEdgeRepository,
    DbPipelineRepository,
    DbPipelineRunRepository,
    DbPipelineStepRepository,
    DbPipelineStepRunRepository,
    Engine,
    Factory as DbFactory,
    transaction,
)
from domain.store.files.store import LocalFileRepository, StoredFile
from domain.store.redis.repository import Client as RedisClient
from models.domain.atlassian import AtlassianFavorite, AtlassianSettings, FavoriteKind
from models.domain.chatbot import AutomationCacheEntry, Chatbot, ChatMessage, Conversation
from models.domain.copilot import CopilotMessage, CopilotModelUsage, CopilotSession, CopilotSessionStatus, CopilotTurnRecord
from models.domain.pipeline import Pipeline, PipelineRun, PipelineStepRun, RunStatus


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

        self._atlassian_repository = DbAtlassianRepository(engine)
        self._atlassian_favorite_repository = DbAtlassianFavoriteRepository(engine)
        self._chatbot_repository = DbChatbotRepository(engine)
        self._conversation_repository = DbConversationRepository(engine)
        self._message_repository = DbMessageRepository(engine)
        self._automation_cache_repository = DbAutomationCacheRepository(engine)
        self._pipeline_repository = DbPipelineRepository(engine)
        self._pipeline_step_repository = DbPipelineStepRepository(engine)
        self._pipeline_edge_repository = DbPipelineEdgeRepository(engine)
        self._pipeline_run_repository = DbPipelineRunRepository(engine)
        self._pipeline_step_run_repository = DbPipelineStepRunRepository(engine)
        self._copilot_session_repository = DbCopilotSessionRepository(engine)
        self._copilot_message_repository = DbCopilotMessageRepository(engine)
        self._copilot_turn_repository = DbCopilotTurnRepository(engine)
        self._files_repository = LocalFileRepository(config.project_data_root)
        self._definitions_repository = LocalFileRepository(config.definitions_root)
        self._secret_box = SecretBox(config.secret_key)

    # -------------------------------------------------------------- chatbots
    def list_chatbots(self, project_name: str) -> list[Chatbot]:
        return [DbAdapter.to_chatbot(row) for row in self._chatbot_repository.list_for_project(project_name)]

    def get_chatbot(self, chatbot_id: int) -> Chatbot | None:
        row = self._chatbot_repository.get(chatbot_id)
        return DbAdapter.to_chatbot(row) if row else None

    def save_chatbot(self, chatbot: Chatbot) -> Chatbot:
        return DbAdapter.to_chatbot(self._chatbot_repository.save(DbFactory.to_chatbot_row(chatbot)))

    def delete_chatbot(self, chatbot_id: int) -> bool:
        """Its conversations and messages go with it (DB cascade)."""
        return self._chatbot_repository.delete(chatbot_id)

    def list_conversations(self, chatbot_id: int) -> list[Conversation]:
        """Most recently updated first."""
        return [DbAdapter.to_conversation(row) for row in self._conversation_repository.list_for_chatbot(chatbot_id)]

    def get_conversation(self, conversation_id: int) -> Conversation | None:
        row = self._conversation_repository.get(conversation_id)
        return DbAdapter.to_conversation(row) if row else None

    def save_conversation(self, conversation: Conversation) -> Conversation:
        return DbAdapter.to_conversation(self._conversation_repository.save(DbFactory.to_conversation_row(conversation)))

    def delete_conversation(self, conversation_id: int) -> bool:
        """Its messages go with it (DB cascade)."""
        return self._conversation_repository.delete(conversation_id)

    def list_messages(self, conversation_id: int) -> list[ChatMessage]:
        """Oldest first."""
        return [DbAdapter.to_message(row) for row in self._message_repository.list_for_conversation(conversation_id)]

    def get_message(self, message_id: int) -> ChatMessage | None:
        row = self._message_repository.get(message_id)
        return DbAdapter.to_message(row) if row else None

    def save_message(self, message: ChatMessage) -> ChatMessage:
        return DbAdapter.to_message(self._message_repository.save(DbFactory.to_message_row(message)))

    def list_automation_cache_entries(self, chatbot_id: int) -> list[AutomationCacheEntry]:
        """A chatbot's cache entries, oldest first."""
        return [DbAdapter.to_automation_cache_entry(row) for row in self._automation_cache_repository.list_for_chatbot(chatbot_id)]

    def get_automation_cache_entry(self, entry_id: int) -> AutomationCacheEntry | None:
        row = self._automation_cache_repository.get(entry_id)
        return DbAdapter.to_automation_cache_entry(row) if row else None

    def save_automation_cache_entry(self, entry: AutomationCacheEntry) -> AutomationCacheEntry:
        return DbAdapter.to_automation_cache_entry(self._automation_cache_repository.save(DbFactory.to_automation_cache_row(entry)))

    def delete_automation_cache_entry(self, entry_id: int) -> bool:
        return self._automation_cache_repository.delete(entry_id)

    # ------------------------------------------------------------- pipelines
    def list_pipelines(self, project_name: str) -> list[Pipeline]:
        """With their steps, sorted by name."""
        rows = self._pipeline_repository.list_for_project(project_name)
        ids = [row.id for row in rows]
        steps = self._pipeline_step_repository.list_for_pipelines(ids)
        edges = self._pipeline_edge_repository.list_for_pipelines(ids)
        return [DbAdapter.to_pipeline(row, steps[row.id], edges[row.id]) for row in rows]

    def get_pipeline(self, pipeline_id: int) -> Pipeline | None:
        row = self._pipeline_repository.get(pipeline_id)
        return self._with_steps(row) if row else None

    def save_pipeline(self, pipeline: Pipeline) -> Pipeline:
        """The pipeline and exactly its steps (in their order) and edges, all
        in one transaction: a failure leaves the saved pipeline as it was."""
        with transaction(self._engine):
            row = self._pipeline_repository.save(DbFactory.to_pipeline_row(pipeline))
            step_rows = [DbFactory.to_pipeline_step_row(step, row.id, position) for position, step in enumerate(pipeline.steps)]
            saved_steps = self._pipeline_step_repository.replace(row.id, step_rows)
            step_ids = {step_row.name: step_row.id for step_row in saved_steps}
            edge_rows = [DbFactory.to_pipeline_edge_row(edge, row.id, step_ids) for edge in pipeline.edges]
            saved_edges = self._pipeline_edge_repository.replace(row.id, edge_rows)
        return DbAdapter.to_pipeline(row, saved_steps, saved_edges)

    def delete_pipeline(self, pipeline_id: int) -> bool:
        """Its steps and runs go with it (DB cascade)."""
        return self._pipeline_repository.delete(pipeline_id)

    def _with_steps(self, row) -> Pipeline:
        return DbAdapter.to_pipeline(
            row, self._pipeline_step_repository.list_for_pipeline(row.id),
            self._pipeline_edge_repository.list_for_pipeline(row.id),
        )

    def save_pipeline_run(self, run: PipelineRun) -> PipelineRun:
        """The run only (its steps are saved one by one with ``save_pipeline_step_run``)."""
        return DbAdapter.to_pipeline_run(self._pipeline_run_repository.save(DbFactory.to_pipeline_run_row(run)))

    def get_pipeline_run(self, run_id: int) -> PipelineRun | None:
        """With its steps."""
        row = self._pipeline_run_repository.get(run_id)
        return DbAdapter.to_pipeline_run(row, self._pipeline_step_run_repository.list_for_run(row.id)) if row else None

    def list_pipeline_runs(self, pipeline_id: int, limit: int = 20) -> list[PipelineRun]:
        """With their steps, newest first."""
        rows = self._pipeline_run_repository.list_for_pipeline(pipeline_id, limit)
        step_runs = self._pipeline_step_run_repository.list_for_runs([row.id for row in rows])
        return [DbAdapter.to_pipeline_run(row, step_runs[row.id]) for row in rows]

    def delete_pipeline_run(self, run_id: int) -> bool:
        """Its step runs go with it (DB cascade); the agent runs stay."""
        return self._pipeline_run_repository.delete(run_id)

    def list_pipeline_runs_by_status(self, status: RunStatus) -> list[PipelineRun]:
        return [DbAdapter.to_pipeline_run(row) for row in self._pipeline_run_repository.list_by_status(status.value)]

    def claim_next_pipeline_run(self) -> PipelineRun | None:
        """The oldest queued run, already switched to RUNNING (worker queue)."""
        row = self._pipeline_run_repository.claim_next()
        return DbAdapter.to_pipeline_run(row) if row else None

    def save_pipeline_step_run(self, step_run: PipelineStepRun) -> PipelineStepRun:
        row = self._pipeline_step_run_repository.save(DbFactory.to_pipeline_step_run_row(step_run))
        return DbAdapter.to_pipeline_step_run(row)

    # ------------------------------------------------------------- atlassian
    def get_atlassian_settings(self, project_name: str) -> AtlassianSettings | None:
        """The API token comes back decrypted; empty when it cannot be (key
        changed or missing), so the project shows as not configured."""
        row = self._atlassian_repository.get(project_name)
        if row is None:
            return None
        token = self._secret_box.decrypt(row.api_token) if self._secret_box.is_configured else None
        if token is None:
            log_warning(LogPrefix.STORE_SERVICE, "Token Atlassian di %s non decifrabile", project_name)
        return DbAdapter.to_atlassian_settings(row, api_token=token or "")

    def save_atlassian_settings(self, settings: AtlassianSettings) -> AtlassianSettings:
        """The API token is saved encrypted."""
        encrypted = self._secret_box.encrypt(settings.api_token.get_secret_value())
        self._atlassian_repository.save(DbFactory.to_atlassian_row(settings, encrypted_token=encrypted))
        return settings

    def delete_atlassian_settings(self, project_name: str) -> bool:
        return self._atlassian_repository.delete(project_name)

    def list_atlassian_favorites(self, project_name: str) -> list[AtlassianFavorite]:
        return [DbAdapter.to_atlassian_favorite(row) for row in self._atlassian_favorite_repository.list_for_project(project_name)]

    def find_atlassian_favorite(self, project_name: str, kind: FavoriteKind, ref: str) -> AtlassianFavorite | None:
        row = self._atlassian_favorite_repository.find(project_name, kind.value, ref)
        return DbAdapter.to_atlassian_favorite(row) if row else None

    def get_atlassian_favorite(self, favorite_id: int) -> AtlassianFavorite | None:
        row = self._atlassian_favorite_repository.get(favorite_id)
        return DbAdapter.to_atlassian_favorite(row) if row else None

    def save_atlassian_favorite(self, favorite: AtlassianFavorite) -> AtlassianFavorite:
        row = self._atlassian_favorite_repository.save(DbFactory.to_atlassian_favorite_row(favorite))
        return DbAdapter.to_atlassian_favorite(row)

    def delete_atlassian_favorite(self, favorite_id: int) -> bool:
        return self._atlassian_favorite_repository.delete(favorite_id)

    def delete_atlassian_favorites_of_other_sites(self, project_name: str, site: str) -> int:
        return self._atlassian_favorite_repository.delete_other_sites(project_name, site)

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
