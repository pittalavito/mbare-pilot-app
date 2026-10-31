"""Builds every store once, on the same backends.

Only the composition root (``Container``) and the tests use it: services never
receive a ``Stores``, only the single stores they need. It exists so that the
connections (Postgres engine, Redis client) are opened once and the tests can
put in-memory backends under every store at once."""
import redis
from sqlalchemy.engine import Engine as SqlAlchemyEngine

from config import Config
from core.secret_box import SecretBox
from domain.store.db.repository import Engine
from domain.store.redis.repository import Client as RedisClient
from service.store.agent_store import AgentStore
from service.store.atlassian_store import AtlassianStore
from service.store.catalog_store import CatalogStore
from service.store.chatbot_store import ChatbotStore
from service.store.copilot_store import CopilotStore
from service.store.definition_store import DefinitionStore
from service.store.mask_store import MaskStore
from service.store.pipeline_store import PipelineStore
from service.store.project_file_store import ProjectFileStore
from service.store.project_store import ProjectStore
from service.store.run_store import RunStore
from service.store.worker_store import WorkerStore


class Stores:

    def __init__(self, engine: SqlAlchemyEngine | None = None, redis_client: redis.Redis | None = None):
        """Connects to Postgres and Redis from the Config; tests pass their own
        ``engine`` (in-memory SQLite) and ``redis_client`` (fakeredis)."""
        config = Config.get()
        self.engine = engine if engine is not None else Engine.create_db_engine(config.database_url)
        self.redis_client = redis_client if redis_client is not None else RedisClient.create_redis_client(config.redis_url)
        # Postgres
        self.runs = RunStore(self.engine, self.redis_client)  # with the traces in Redis
        self.catalog = CatalogStore(self.engine)
        self.agents = AgentStore(self.engine)
        self.projects = ProjectStore(self.engine)
        self.chatbots = ChatbotStore(self.engine)
        self.pipelines = PipelineStore(self.engine)
        self.copilot = CopilotStore(self.engine)
        self.atlassian = AtlassianStore(self.engine, SecretBox(config.secret_key))
        # Redis
        self.workers = WorkerStore(self.redis_client)
        self.masks = MaskStore(self.redis_client)
        # files under <data_home>
        self.project_files = ProjectFileStore(config.project_data_root)
        self.definitions = DefinitionStore(config.definitions_root)
