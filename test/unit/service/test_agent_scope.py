"""Roles and configs are global (project_name None) or owned by one project."""
import pytest

from core.error import ConflictError, ValidationError
from models.domain.agent import AgentConfig, AgentRole
from models.domain.project import Project, ProjectSource


@pytest.fixture
def project(project_store):
    return project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path="/tmp/acme"))


def _config(service, name: str, role: str, project_name: str | None) -> AgentConfig:
    return AgentConfig(
        name=name, project_name=project_name, role_name=role,
        prompt_id=service.latest_prompt(role).id, model="openai/gpt-4o",
    )


def _project_role(service, name: str = "acme-role") -> None:
    service.save_role(AgentRole(name=name, project_name="acme"), create=True)
    service.create_prompt_version(name, "Prompt di progetto")


def test_listing_by_scope(agent_config_service, project):
    _project_role(agent_config_service)
    agent_config_service.save_config(_config(agent_config_service, "acme-bot", "acme-role", "acme"), create=True)

    assert [r.name for r in agent_config_service.list_roles()] == ["hello"]
    assert [r.name for r in agent_config_service.list_roles("acme")] == ["acme-role", "hello"]
    assert [r.name for r in agent_config_service.list_roles("acme", include_global=False)] == ["acme-role"]
    assert [c.name for c in agent_config_service.list_configs()] == ["hello"]
    assert [c.name for c in agent_config_service.list_configs("acme")] == ["acme-bot", "hello"]
    assert [c.name for c in agent_config_service.list_configs("acme", include_global=False)] == ["acme-bot"]


def test_project_config_may_use_global_role(agent_config_service, project):
    saved = agent_config_service.save_config(_config(agent_config_service, "acme-hello", "hello", "acme"), create=True)

    assert saved.project_name == "acme"
    assert agent_config_service.resolve("acme-hello").config.project_name == "acme"


def test_global_config_cannot_use_project_role(agent_config_service, project):
    _project_role(agent_config_service)

    with pytest.raises(ValidationError, match="acme"):
        agent_config_service.save_config(_config(agent_config_service, "global-bot", "acme-role", None), create=True)


def test_config_cannot_use_role_of_another_project(agent_config_service, project, project_store):
    project_store.save(Project(name="other", source=ProjectSource.FOLDER, root_path="/tmp/other"))
    _project_role(agent_config_service)

    with pytest.raises(ValidationError):
        agent_config_service.save_config(_config(agent_config_service, "x", "acme-role", "other"), create=True)


def test_scope_cannot_change_on_update(agent_config_service, project):
    with pytest.raises(ValidationError, match="scope"):
        agent_config_service.save_config(_config(agent_config_service, "hello", "hello", "acme"))


def test_role_scope_is_kept_on_update(agent_config_service, project):
    _project_role(agent_config_service)

    updated = agent_config_service.save_role(AgentRole(name="acme-role", description="nuova", project_name=None))

    assert updated.project_name == "acme" and updated.description == "nuova"


def test_unknown_project_and_duplicate_names_rejected(agent_config_service, project):
    with pytest.raises(ValidationError):
        agent_config_service.save_role(AgentRole(name="ghost-role", project_name="ghost"), create=True)
    with pytest.raises(ConflictError):
        agent_config_service.save_role(AgentRole(name="hello"), create=True)


def test_run_records_project_of_the_config(agent_config_service, project, monkeypatch, make_agent_service, run_store):
    from fakes import FakeAgent
    from models.domain.agent import RunOrigin
    from service import agent_service as agent_service_module
    from service.chat_service import ChatService

    chat = ChatService()
    monkeypatch.setattr(chat, "get_client", lambda model: object())
    monkeypatch.setattr(agent_service_module.AgentFactory, "create_agent", staticmethod(lambda spec, c, t: FakeAgent()))
    agent_config_service.save_config(_config(agent_config_service, "acme-hello", "hello", "acme"), create=True)

    record = make_agent_service(chat).run("acme-hello", "ciao", origin=RunOrigin.CHAT)

    [summary] = run_store.list_runs()
    assert (record.project_name, summary.project_name, summary.origin) == ("acme", "acme", "chat")
