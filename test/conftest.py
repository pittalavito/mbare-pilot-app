"""Shared fixtures: real repositories on in-memory backends (SQLite, fakeredis,
tmp dir), so unit tests need neither Docker nor API keys."""
import fakeredis
import pytest
from cryptography.fernet import Fernet
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

import models.store.db  # noqa: F401  (registers the tables)
from config import Config
from domain.chat.models_default import DEFAULT_CHAT_MODELS
from domain.store.files.store import LocalFileRepository
from models.domain.agent import AgentConfig, AgentRole
from service.agent_config_service import AgentConfigService
from service.store_service import StoreService

HELLO_AGENT = """agents:
  - name: hello
    description: Agente di esempio con i tool hello_world
    role: hello
    model: openai/gpt-4o
    tools: [hello_world]
    system_prompt: Sei un assistente. Usa i tool a disposizione quando servono.
"""
"""The example agent the tests build on, as the data folder's global-agent.yml
has it: a Container creates it at startup, as in the app."""

CODING_AGENT = """plan_prompt: |
  Ti affido il task qui sotto. Leggi il codice, fai le tue domande e aspetta il mio ok.

  {task}
execute_prompt: Ok, procedi con il piano concordato, senza commit.
denied_tools: ["shell(git commit)", "shell(git push)", "shell(git reset)"]
"""
"""Copilot's prompts and denied tools (global-coding-agent.yml): required to use Copilot."""


@pytest.fixture(autouse=True)
def config(tmp_path):
    """The app-wide Config for every test: no .env, fake URLs and keys, no real
    Copilot CLI (a Container's client finds none until a test gives it the fake), data in
    a tmp dir whose definition/ holds the example agent and Copilot's definition."""
    test_config = Config(
        _env_file=None,
        database_url="sqlite://",
        redis_url="redis://unused",
        openai_api_key="test",
        mbare_pilot_home=str(tmp_path / "home"),
        mbare_pilot_secret_key=Fernet.generate_key().decode(),
        copilot_command="copilot-disabled-in-tests",  # never the real CLI (it spends AI credits): tests use test/fake_copilot.py
    )
    test_config.definitions_root.mkdir(parents=True)
    (test_config.definitions_root / "global-agent.yml").write_text(HELLO_AGENT, encoding="utf-8")
    (test_config.definitions_root / "global-coding-agent.yml").write_text(CODING_AGENT, encoding="utf-8")
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
    return LocalFileRepository(config.project_data_root)


@pytest.fixture
def store_service(engine, redis_client):
    service = StoreService(engine=engine, redis_client=redis_client)
    service.seed_chat_models(DEFAULT_CHAT_MODELS)
    return service


@pytest.fixture
def agent_config_service(store_service):
    """AgentConfigService on the in-memory store with the tool catalog and the
    example agent the tests build on: global role ``hello``, prompt v1, agent
    ``hello`` with ``hello_world`` (in the app it comes from global-agent.yml)."""
    service = AgentConfigService(store_service)
    service.sync_tools()
    if store_service.get_agent_config("hello") is None:  # a Container may have created it already
        service.save_role(AgentRole(name="hello", description="Assistente di esempio che saluta e conta parole."), create=True)
        prompt = service.create_prompt_version("hello", "Sei un assistente. Usa i tool a disposizione quando servono.")
        service.save_config(AgentConfig(
            name="hello", description="Agente di esempio con i tool hello_world", role_name="hello",
            prompt_id=prompt.id, model="openai/gpt-4o", tool_names=["hello_world"],
        ))
    return service
