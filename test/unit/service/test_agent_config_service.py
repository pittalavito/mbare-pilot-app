import pytest

from core.error import ValidationError
from models.domain.agent import AgentConfig, AgentRole, ToolInfo
from tool.registry import TOOL_REGISTRY


def _config(service, **overrides) -> AgentConfig:
    values = dict(
        name="cfg", role_name="hello", prompt_id=service.latest_prompt("hello").id,
        model="openai/gpt-4o", tool_names=["hello_world"],
    )
    values.update(overrides)
    return AgentConfig(**values)


# ---------------------------------------------------------------- catalog
def test_sync_tools_registers_every_implemented_tool(agent_config_service):
    agent_config_service.sync_tools()  # twice: no duplicates

    assert {t.name for t in agent_config_service.list_tools()} == set(TOOL_REGISTRY)


# ------------------------------------------------------------------- prompts
def test_new_prompt_version_increments(agent_config_service):
    created = agent_config_service.create_prompt_version("hello", "Nuovo prompt")

    assert created.version == 2
    assert [p.version for p in agent_config_service.list_prompts("hello")] == [2, 1]


def test_identical_prompt_does_not_create_a_version(agent_config_service):
    latest = agent_config_service.latest_prompt("hello")

    assert agent_config_service.create_prompt_version("hello", f"  {latest.text}  ").id == latest.id
    assert len(agent_config_service.list_prompts("hello")) == 1


def test_config_keeps_its_pinned_prompt_version(agent_config_service):
    agent_config_service.create_prompt_version("hello", "Nuovo prompt")

    assert agent_config_service.resolve("hello").prompt.version == 1


@pytest.mark.parametrize("role, text", [("missing", "x"), ("hello", "   ")])
def test_invalid_prompt_rejected(agent_config_service, role, text):
    with pytest.raises(ValidationError):
        agent_config_service.create_prompt_version(role, text)


# ------------------------------------------------------------------- configs
def test_save_and_resolve_config(agent_config_service):
    agent_config_service.save_config(_config(agent_config_service))

    spec = agent_config_service.resolve("cfg")
    assert spec.config.tool_names == ["hello_world"]
    assert spec.prompt.role_name == "hello"


def test_config_rejects_prompt_of_another_role(agent_config_service):
    agent_config_service.save_role(AgentRole(name="other"))
    other_prompt = agent_config_service.create_prompt_version("other", "Altro")

    with pytest.raises(ValidationError):
        agent_config_service.save_config(_config(agent_config_service, prompt_id=other_prompt.id))


def test_config_rejects_unknown_tool(agent_config_service):
    with pytest.raises(ValidationError):
        agent_config_service.save_config(_config(agent_config_service, tool_names=["not_a_tool"]))


def test_config_rejects_unknown_role(agent_config_service):
    with pytest.raises(ValidationError):
        agent_config_service.save_config(_config(agent_config_service, role_name="missing"))


def test_delete_config(agent_config_service):
    assert agent_config_service.delete_config("hello") is True
    assert agent_config_service.list_configs() == []


# --------------------------------------------------------------------- tools
def test_tool_removed_from_code_is_unavailable(agent_config_service, catalog_store):
    catalog_store.sync_tools([ToolInfo(name="legacy_tool", description="old")])

    tools = {t.name: t for t in agent_config_service.list_tools()}
    assert tools["legacy_tool"].available is False
    assert tools["hello_world"].available is True
    with pytest.raises(ValidationError):
        agent_config_service.save_config(_config(agent_config_service, tool_names=["legacy_tool"]))


def test_create_with_existing_name_conflicts(agent_config_service):
    from core.error import ConflictError

    with pytest.raises(ConflictError):
        agent_config_service.save_config(_config(agent_config_service, name="hello"), create=True)
    assert agent_config_service.get_config("hello").tool_names == ["hello_world"]


def test_update_existing_name_is_allowed(agent_config_service):
    agent_config_service.save_config(_config(agent_config_service, name="hello", tool_names=[]))

    assert agent_config_service.get_config("hello").tool_names == []
