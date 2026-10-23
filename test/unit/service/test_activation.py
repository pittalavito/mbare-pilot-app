"""Roles and prompt versions are toggled on/off, never deleted."""
import pytest

from core.error import NotFoundError, ValidationError
from models.domain.agent import AgentConfig


def _config(service, **overrides) -> AgentConfig:
    values = dict(
        name="cfg", role_name="hello", prompt_id=service.latest_prompt("hello").id,
        model="openai/gpt-4o", tool_names=["hello_world"],
    )
    values.update(overrides)
    return AgentConfig(**values)


# --------------------------------------------------------------------- roles
def test_inactive_role_blocks_run_and_save(agent_config_service):
    agent_config_service.set_role_active("hello", False)

    assert agent_config_service.list_roles()[0].active is False
    with pytest.raises(ValidationError, match="disattivato"):
        agent_config_service.resolve("hello")
    with pytest.raises(ValidationError):
        agent_config_service.save_config(_config(agent_config_service))
    assert "disattivato" in agent_config_service.blocked_reason(agent_config_service.get_config("hello"))


def test_reactivated_role_runs_again(agent_config_service):
    agent_config_service.set_role_active("hello", False)
    agent_config_service.set_role_active("hello", True)

    assert agent_config_service.resolve("hello").config.role_name == "hello"
    assert agent_config_service.blocked_reason(agent_config_service.get_config("hello")) is None


def test_deactivating_keeps_role_prompts_and_configs(agent_config_service):
    agent_config_service.set_role_active("hello", False)

    assert [r.name for r in agent_config_service.list_roles()] == ["hello"]
    assert len(agent_config_service.list_prompts("hello")) == 1
    assert [c.name for c in agent_config_service.list_configs()] == ["hello"]


def test_toggle_unknown_role_raises(agent_config_service):
    with pytest.raises(NotFoundError):
        agent_config_service.set_role_active("missing", False)


# ------------------------------------------------------------------- prompts
def test_inactive_prompt_blocks_pinned_configs_only(agent_config_service):
    v1 = agent_config_service.latest_prompt("hello")
    v2 = agent_config_service.create_prompt_version("hello", "Seconda versione")
    agent_config_service.save_config(_config(agent_config_service, name="on-v2", prompt_id=v2.id))

    agent_config_service.set_prompt_active(v1.id, False)

    with pytest.raises(ValidationError, match="v1"):
        agent_config_service.resolve("hello")
    assert agent_config_service.resolve("on-v2").prompt.version == 2


def test_deactivating_prompt_keeps_its_text(agent_config_service):
    v1 = agent_config_service.latest_prompt("hello")

    toggled = agent_config_service.set_prompt_active(v1.id, False)

    assert toggled.active is False and toggled.text == v1.text and toggled.version == 1
    assert agent_config_service.set_prompt_active(v1.id, True).active is True
    assert agent_config_service.resolve("hello").prompt.id == v1.id


def test_inactive_prompt_cannot_be_picked(agent_config_service):
    v1 = agent_config_service.latest_prompt("hello")
    agent_config_service.set_prompt_active(v1.id, False)

    with pytest.raises(ValidationError):
        agent_config_service.save_config(_config(agent_config_service, prompt_id=v1.id))


def test_latest_active_prompt_skips_inactive_versions(agent_config_service):
    v1 = agent_config_service.latest_prompt("hello")
    v2 = agent_config_service.create_prompt_version("hello", "Seconda versione")
    agent_config_service.set_prompt_active(v2.id, False)

    assert agent_config_service.latest_prompt("hello").id == v2.id
    assert agent_config_service.latest_active_prompt("hello").id == v1.id


def test_toggle_unknown_prompt_raises(agent_config_service):
    with pytest.raises(NotFoundError):
        agent_config_service.set_prompt_active(9999, False)


# ----------------------------------------------------------------------- run
def test_agent_service_refuses_inactive_role(agent_config_service, store_service, monkeypatch):
    from service.agent_service import AgentService
    from service.chat_service import ChatService
    from service.git_service import GitService

    chat_service = ChatService()
    monkeypatch.setattr(chat_service, "get_client", lambda model: object())
    agent_service = AgentService(
        chat_service=chat_service, agent_config_service=agent_config_service, store_service=store_service,
        git_service=GitService(store_service),
    )
    agent_config_service.set_role_active("hello", False)

    with pytest.raises(ValidationError):
        agent_service.run("hello", "ciao")
    assert store_service.list_runs() == []
