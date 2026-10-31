"""Builds every store once, on the same backends.

Only the composition root (``Container``) and the tests use it: services never
receive a ``Stores``, only the single stores they need. It exists so that the
connections (Postgres engine, Redis client) are opened once and the tests can
put in-memory backends under every store at once."""
import redis
from sqlalchemy.engine import Engine as SqlAlchemyEngine

from config import Config
from domain.store.db.repository import Engine
from domain.store.redis.repository import Client as RedisClient
from service.store_service import StoreService


class Stores:

    def __init__(self, engine: SqlAlchemyEngine | None = None, redis_client: redis.Redis | None = None):
        """Connects to Postgres and Redis from the Config; tests pass their own
        ``engine`` (in-memory SQLite) and ``redis_client`` (fakeredis)."""
        config = Config.get()
        self.engine = engine if engine is not None else Engine.create_db_engine(config.database_url)
        self.redis_client = redis_client if redis_client is not None else RedisClient.create_redis_client(config.redis_url)
        self.store_service = StoreService(engine=self.engine, redis_client=self.redis_client)
