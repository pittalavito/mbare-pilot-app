"""Single persistence facade for the app.

Builds and composes every repository behind one service-layer object: the DB
repositories (run facts), the Redis repositories (verbatim traces, cache, ...)
and the local file store, all from ``Config.get()``. The repositories deal only
in rows/records; the per-store ``Adapter``/``Factory`` translate to and from the
domain models.
"""
import redis
from sqlalchemy.engine import Engine as SqlAlchemyEngine

from config import Config
from core.observability import LogPrefix, log_warning
from core.secret_box import SecretBox
from domain.chat.pricing import PriceList
from domain.store.db.store import (
    Adapter as DbAdapter,
    DbAgentConfigRepository,
    DbAtlassianFavoriteRepository,
    DbAtlassianRepository,
    DbChatbotRepository,
    DbConversationRepository,
    DbMessageRepository,
    DbPipelineRepository,
    DbPipelineRunRepository,
    DbPipelineStepRepository,
    DbPipelineStepRunRepository,
    DbChatModelRepository,
    DbProjectRepository,
    DbPromptRepository,
    DbRoleRepository,
    DbRunRepository,
    DbToolRepository,
    Engine,
    Factory as DbFactory,
)
from domain.store.files.store import LocalFileRepository, StoredFile
from domain.store.redis.store import (
    Adapter as RedisAdapter, Client as RedisClient, Factory as RedisFactory, RedisTraceRepository, RedisWorkerRepository,
)
from models.domain.agent import AgentConfig, AgentRole, AgentRunRecord, AgentRunSummary, SystemPrompt, ToolCallSummary, ToolInfo
from models.domain.atlassian import AtlassianFavorite, AtlassianSettings, FavoriteKind
from models.domain.chat import ChatModel
from models.domain.chatbot import ChatMessage, Chatbot, Conversation
from models.domain.pipeline import Pipeline, PipelineRun, PipelineStepRun, RunStatus
from models.domain.project import Project, ProjectSource
from models.domain.worker import WorkerStatus
from models.store.redis import AgentTraceRecord


class StoreService:

    def __init__(self, engine: SqlAlchemyEngine | None = None, redis_client: redis.Redis | None = None):
        """Connects to Postgres and Redis from the Config; tests pass their own
        ``engine`` (in-memory SQLite) and ``redis_client`` (fakeredis)."""
        config = Config.get()
        if engine is None:
            engine = Engine.create_db_engine(config.database_url)
        if redis_client is None:
            redis_client = RedisClient.create_redis_client(config.redis_url)

        self._runs_repository = DbRunRepository(engine)
        self._chat_model_repository = DbChatModelRepository(engine)
        self._role_repository = DbRoleRepository(engine)
        self._prompt_repository = DbPromptRepository(engine)
        self._tool_repository = DbToolRepository(engine)
        self._agent_config_repository = DbAgentConfigRepository(engine)
        self._project_repository = DbProjectRepository(engine)
        self._atlassian_repository = DbAtlassianRepository(engine)
        self._atlassian_favorite_repository = DbAtlassianFavoriteRepository(engine)
        self._chatbot_repository = DbChatbotRepository(engine)
        self._conversation_repository = DbConversationRepository(engine)
        self._message_repository = DbMessageRepository(engine)
        self._pipeline_repository = DbPipelineRepository(engine)
        self._pipeline_step_repository = DbPipelineStepRepository(engine)
        self._pipeline_run_repository = DbPipelineRunRepository(engine)
        self._pipeline_step_run_repository = DbPipelineStepRunRepository(engine)
        self._traces_repository = RedisTraceRepository(redis_client)
        self._workers_repository = RedisWorkerRepository(redis_client)
        self._files_repository = LocalFileRepository(config.projects_data_root)
        self._secret_box = SecretBox(config.secret_key)

    # ------------------------------------------------------------------ runs
    def save_run(self, record: AgentRunRecord) -> None:
        """Facts in SQL, verbatim trace in Redis (same run_id)."""
        self._runs_repository.save_rows(DbFactory.to_run_row(record), DbFactory.to_tool_rows(record))
        self._traces_repository.save(RedisFactory.to_trace_record(record))

    def list_runs(self, limit: int = 100) -> list[AgentRunSummary]:
        return [DbAdapter.to_run_summary(row) for row in self._runs_repository.list_recent(limit)]

    def list_tool_calls(self, limit: int = 100) -> list[ToolCallSummary]:
        return [DbAdapter.to_tool_call_summary(row) for row in self._runs_repository.list_recent_tool_calls(limit)]

    def get_run_trace(self, run_id: str) -> AgentTraceRecord | None:
        return self._traces_repository.load(run_id)

    # ----------------------------------------------------------- chat models
    def seed_chat_models(self, seeds: list[ChatModel]) -> int:
        """Insert the seed models not in the catalog yet. Returns how many."""
        return self._chat_model_repository.insert_missing([DbFactory.to_chat_model_row(seed) for seed in seeds])

    def list_chat_models(self) -> list[ChatModel]:
        """Sorted by provider and model id."""
        return [DbAdapter.to_chat_model(row) for row in self._chat_model_repository.list_sorted()]

    def get_chat_model(self, key: str) -> ChatModel | None:
        """By ``<provider>/<model>`` key; None when not in the catalog."""
        provider, _, model = key.partition("/")
        row = self._chat_model_repository.get((provider, model))
        return DbAdapter.to_chat_model(row) if row else None

    def get_price_list(self) -> PriceList:
        """Keyed by model id, as datapizza names models in its spans."""
        return {chat_model.model: chat_model for chat_model in self.list_chat_models()}

    def save_chat_model(self, chat_model: ChatModel) -> ChatModel:
        return DbAdapter.to_chat_model(self._chat_model_repository.save(DbFactory.to_chat_model_row(chat_model)))

    def delete_chat_model(self, key: str) -> bool:
        provider, _, model = key.partition("/")
        return self._chat_model_repository.delete((provider, model))

    def chat_model_keys_in_use(self) -> set[str]:
        """Models referenced by agent configs, chatbots or pipeline steps."""
        return self._chat_model_repository.keys_in_use()

    # ----------------------------------------------------------------- roles
    def list_roles(self, project_name: str | None = None, include_global: bool = True) -> list[AgentRole]:
        """Global roles (``project_name`` None) or a project's, optionally with the global ones."""
        return [DbAdapter.to_role(row) for row in self._role_repository.list_scoped(project_name, include_global)]

    def get_role(self, name: str) -> AgentRole | None:
        row = self._role_repository.get(name)
        return DbAdapter.to_role(row) if row else None

    def save_role(self, role: AgentRole) -> AgentRole:
        return DbAdapter.to_role(self._role_repository.save(DbFactory.to_role_row(role)))

    def set_role_active(self, name: str, active: bool) -> AgentRole | None:
        """None when the role does not exist."""
        row = self._role_repository.get(name)
        if row is None:
            return None
        row.active = active
        return DbAdapter.to_role(self._role_repository.save(row))

    def seed_roles(self, seeds: list[AgentRole]) -> int:
        return self._role_repository.insert_missing([DbFactory.to_role_row(seed) for seed in seeds])

    # --------------------------------------------------------------- prompts
    def list_prompts(self, role_name: str | None = None) -> list[SystemPrompt]:
        """Prompt versions, newest first."""
        return [DbAdapter.to_prompt(row) for row in self._prompt_repository.list_versions(role_name)]

    def get_prompt(self, prompt_id: int) -> SystemPrompt | None:
        row = self._prompt_repository.get(prompt_id)
        return DbAdapter.to_prompt(row) if row else None

    def create_prompt_version(self, role_name: str, text: str) -> SystemPrompt:
        return DbAdapter.to_prompt(self._prompt_repository.create_version(role_name, text))

    def set_prompt_active(self, prompt_id: int, active: bool) -> SystemPrompt | None:
        """Toggle a version on/off (its text stays untouched). None when absent."""
        row = self._prompt_repository.get(prompt_id)
        if row is None:
            return None
        row.active = active
        return DbAdapter.to_prompt(self._prompt_repository.save(row))

    # ----------------------------------------------------------------- tools
    def list_tools(self, implemented: set[str]) -> list[ToolInfo]:
        """The catalog; ``available`` tells whether each tool is in ``implemented``."""
        return [DbAdapter.to_tool(row, available=row.name in implemented) for row in self._tool_repository.list_sorted()]

    def sync_tools(self, tools: list[ToolInfo]) -> None:
        """Upsert the tools implemented in code (name + description). Catalog
        rows of tools no longer in code are kept, so old configs stay readable."""
        for tool in tools:
            self._tool_repository.save(DbFactory.to_tool_row(tool))

    # ---------------------------------------------------------- agent config
    def list_agent_configs(self, project_name: str | None = None, include_global: bool = True) -> list[AgentConfig]:
        """Global configs (``project_name`` None) or a project's, optionally with the global ones."""
        rows = self._agent_config_repository.list_scoped(project_name, include_global)
        return [DbAdapter.to_agent_config(row) for row in rows]

    def get_agent_config(self, name: str) -> AgentConfig | None:
        row = self._agent_config_repository.get(name)
        return DbAdapter.to_agent_config(row) if row else None

    def save_agent_config(self, config: AgentConfig) -> AgentConfig:
        return DbAdapter.to_agent_config(self._agent_config_repository.save(DbFactory.to_agent_config_row(config)))

    def delete_agent_config(self, name: str) -> bool:
        return self._agent_config_repository.delete(name)

    # -------------------------------------------------------------- projects
    def list_projects(self, source: ProjectSource | None = None) -> list[Project]:
        """Projects, most recent first."""
        rows = self._project_repository.list_recent(source.value if source else None)
        return [DbAdapter.to_project(row) for row in rows]

    def get_project(self, name: str) -> Project | None:
        row = self._project_repository.get(name)
        return DbAdapter.to_project(row) if row else None

    def save_project(self, project: Project) -> Project:
        return DbAdapter.to_project(self._project_repository.save(DbFactory.to_project_row(project)))

    def delete_project(self, name: str) -> bool:
        return self._project_repository.delete(name)

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

    def save_message(self, message: ChatMessage) -> ChatMessage:
        return DbAdapter.to_message(self._message_repository.save(DbFactory.to_message_row(message)))

    # ------------------------------------------------------------- pipelines
    def list_pipelines(self, project_name: str) -> list[Pipeline]:
        """With their steps, sorted by name."""
        return [self._with_steps(row) for row in self._pipeline_repository.list_for_project(project_name)]

    def get_pipeline(self, pipeline_id: int) -> Pipeline | None:
        row = self._pipeline_repository.get(pipeline_id)
        return self._with_steps(row) if row else None

    def save_pipeline(self, pipeline: Pipeline) -> Pipeline:
        """The pipeline and exactly its steps, in their order."""
        row = self._pipeline_repository.save(DbFactory.to_pipeline_row(pipeline))
        step_rows = [DbFactory.to_pipeline_step_row(step, row.id, position) for position, step in enumerate(pipeline.steps)]
        return DbAdapter.to_pipeline(row, self._pipeline_step_repository.replace(row.id, step_rows))

    def delete_pipeline(self, pipeline_id: int) -> bool:
        """Its steps and runs go with it (DB cascade)."""
        return self._pipeline_repository.delete(pipeline_id)

    def _with_steps(self, row) -> Pipeline:
        return DbAdapter.to_pipeline(row, self._pipeline_step_repository.list_for_pipeline(row.id))

    def save_pipeline_run(self, run: PipelineRun) -> PipelineRun:
        """The run only (its steps are saved one by one with ``save_pipeline_step_run``)."""
        return DbAdapter.to_pipeline_run(self._pipeline_run_repository.save(DbFactory.to_pipeline_run_row(run)))

    def get_pipeline_run(self, run_id: int) -> PipelineRun | None:
        """With its steps."""
        row = self._pipeline_run_repository.get(run_id)
        return DbAdapter.to_pipeline_run(row, self._pipeline_step_run_repository.list_for_run(row.id)) if row else None

    def list_pipeline_runs(self, pipeline_id: int, limit: int = 20) -> list[PipelineRun]:
        """With their steps, newest first."""
        return [
            DbAdapter.to_pipeline_run(row, self._pipeline_step_run_repository.list_for_run(row.id))
            for row in self._pipeline_run_repository.list_for_pipeline(pipeline_id, limit)
        ]

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

    # --------------------------------------------------------------- workers
    def save_worker_heartbeat(self, status: WorkerStatus) -> None:
        self._workers_repository.save(RedisFactory.to_heartbeat_record(status))

    def list_workers(self) -> list[WorkerStatus]:
        return [RedisAdapter.to_worker_status(record) for record in self._workers_repository.list_alive()]

    def delete_worker(self, worker_id: str) -> None:
        self._workers_repository.delete(worker_id)

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

    # ----------------------------------------------------------------- files
    def list_files(self, prefix: str = "") -> list[StoredFile]:
        return self._files_repository.list(prefix)

    def save_file(self, file_id: str, data: bytes) -> StoredFile:
        return self._files_repository.save(file_id, data)

    def read_file(self, file_id: str) -> bytes:
        return self._files_repository.read(file_id)

    def delete_file(self, file_id: str) -> bool:
        return self._files_repository.delete(file_id)
