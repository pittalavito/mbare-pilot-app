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
from service.agent_service import AgentService
from service.chat_service import ChatService
from service.copilot_service import CopilotService
from service.git_service import GitService
from service.masking_service import MaskingService
from service.pipeline_service import PipelineService
from service.project_data_service import ProjectDataService
from service.store.stores import Stores

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
    """A file repository on the same root as the ProjectFileStore."""
    return LocalFileRepository(config.project_data_root)


@pytest.fixture
def stores(engine, redis_client):
    """Every store on the in-memory backends, with the default chat models."""
    stores = Stores(engine=engine, redis_client=redis_client)
    stores.catalog.seed_models(DEFAULT_CHAT_MODELS)
    return stores


@pytest.fixture
def worker_store(stores):
    return stores.workers


@pytest.fixture
def mask_store(stores):
    return stores.masks


@pytest.fixture
def run_store(stores):
    return stores.runs


@pytest.fixture
def catalog_store(stores):
    return stores.catalog


@pytest.fixture
def agent_store(stores):
    return stores.agents


@pytest.fixture
def project_store(stores):
    return stores.projects


@pytest.fixture
def chatbot_store(stores):
    return stores.chatbots


@pytest.fixture
def pipeline_store(stores):
    return stores.pipelines


@pytest.fixture
def atlassian_store(stores):
    return stores.atlassian


@pytest.fixture
def copilot_store(stores):
    return stores.copilot


@pytest.fixture
def project_file_store(stores):
    return stores.project_files


@pytest.fixture
def store_service(stores):
    return stores.store_service


@pytest.fixture
def agent_config_service(project_store, agent_store, catalog_store):
    """AgentConfigService on the in-memory store with the tool catalog and the
    example agent the tests build on: global role ``hello``, prompt v1, agent
    ``hello`` with ``hello_world`` (in the app it comes from global-agent.yml)."""
    service = AgentConfigService(project_store, agent_store, catalog_store)
    service.sync_tools()
    if agent_store.get_config("hello") is None:  # a Container may have created it already
        service.save_role(AgentRole(name="hello", description="Assistente di esempio che saluta e conta parole."), create=True)
        prompt = service.create_prompt_version("hello", "Sei un assistente. Usa i tool a disposizione quando servono.")
        service.save_config(AgentConfig(
            name="hello", description="Agente di esempio con i tool hello_world", role_name="hello",
            prompt_id=prompt.id, model="openai/gpt-4o", tool_names=["hello_world"],
        ))
    return service


@pytest.fixture
def git_service(project_store):
    return GitService(project_store)


@pytest.fixture
def project_data_service(project_file_store, project_store):
    return ProjectDataService(project_file_store, project_store)


@pytest.fixture
def masking_service(project_store, mask_store):
    return MaskingService(project_store, mask_store)


@pytest.fixture
def pipeline_service(pipeline_store, project_store, worker_store, catalog_store, agent_store, agent_config_service):
    return PipelineService(pipeline_store, project_store, worker_store, catalog_store, agent_store, agent_config_service)


@pytest.fixture
def make_agent_service(store_service, run_store, catalog_store, copilot_store, agent_config_service,
                       git_service, project_data_service, masking_service, pipeline_service):
    """Builds an AgentService on the in-memory stores, with every service it
    needs, as the Container does. A test passes the ones it drives itself (a
    ChatService with a fake client, its own PipelineService, ...)."""

    def make(chat_service: ChatService | None = None, **services) -> AgentService:
        git = services.pop("git_service", None) or git_service
        data = services.pop("project_data_service", None) or project_data_service
        pipelines = services.pop("pipeline_service", None) or pipeline_service
        masking = services.pop("masking_service", None) or masking_service
        copilot = services.pop("copilot_service", None) or CopilotService.from_config(store_service, copilot_store, git, data)
        assert not services, f"servizi sconosciuti: {sorted(services)}"
        return AgentService(
            chat_service=chat_service or ChatService(), agent_config_service=agent_config_service,
            store_service=store_service, runs=run_store, catalog=catalog_store, git_service=git, pipeline_service=pipelines,
            masking_service=masking, project_data_service=data, copilot_service=copilot,
        )

    return make
