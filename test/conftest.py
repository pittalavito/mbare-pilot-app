"""Shared fixtures: real repositories on in-memory backends (SQLite, fakeredis,
tmp dir), so unit tests need neither Docker nor API keys."""
import fakeredis
import pytest
from cryptography.fernet import Fernet
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

import models.store.db  # noqa: F401  (registers the tables)
from config import Config
from domain.agent.defaults import DEFAULT_CONFIGS, DEFAULT_PROMPTS, DEFAULT_ROLES
from domain.chat.models_default import DEFAULT_CHAT_MODELS
from domain.store.files.store import LocalFileRepository
from service.agent_config_service import AgentConfigService
from service.store_service import StoreService


@pytest.fixture(autouse=True)
def config(tmp_path):
    """The app-wide Config for every test: no .env, fake URLs and keys, data in a tmp dir."""
    test_config = Config(
        _env_file=None,
        database_url="sqlite://",
        redis_url="redis://unused",
        openai_api_key="test",
        mbare_pilot_home=str(tmp_path / "home"),
        mbare_pilot_secret_key=Fernet.generate_key().decode(),
    )
    Config.set(test_config)
    yield test_config
    Config.set(None)


@pytest.fixture
def engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def redis_client():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def files_repository(config):
    """A file repository on the same root the StoreService uses."""
    return LocalFileRepository(config.projects_data_root)


@pytest.fixture
def store_service(engine, redis_client):
    service = StoreService(engine=engine, redis_client=redis_client)
    service.seed_chat_models(DEFAULT_CHAT_MODELS)
    return service


@pytest.fixture
def agent_config_service(store_service):
    """AgentConfigService on the in-memory store, seeded with the defaults
    (role ``hello``, prompt v1, config ``hello``)."""
    service = AgentConfigService(store_service)
    service.seed_defaults(DEFAULT_ROLES, DEFAULT_PROMPTS, DEFAULT_CONFIGS)
    return service
