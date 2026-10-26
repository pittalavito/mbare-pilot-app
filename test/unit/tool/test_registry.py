import pytest

from core.error import ValidationError
from service.git_service import GitService
from tool.context import ToolContext
from tool.registry import TOOL_REGISTRY, build_tools


@pytest.fixture
def context(store_service):
    return ToolContext(project_name=None, git=GitService(store_service))


def test_registry_is_keyed_by_tool_name():
    assert all(name == spec.name for name, spec in TOOL_REGISTRY.items())


def test_every_spec_builds_a_tool_with_its_name_and_a_description(context):
    for name, spec in TOOL_REGISTRY.items():
        assert spec.description
        assert spec.build(context).name == name


def test_only_the_automation_and_copilot_tools_are_for_chatbots_and_the_catalog_says_so(agent_config_service):
    assert {name for name, spec in TOOL_REGISTRY.items() if spec.chatbot_only} == {
        "list_automations", "run_automation", "automation_status", "list_agent_tasks", "delegate_task", "copilot_status",
    }

    agent_config_service.sync_tools()
    flags = {tool.name: tool.chatbot_only for tool in agent_config_service.list_tools()}

    assert flags["run_automation"] and flags["automation_status"] and not flags["git_status"]


def test_build_tools_keeps_order(context):
    assert [t.name for t in build_tools(["git_status", "hello_world"], context)] == ["git_status", "hello_world"]


def test_build_tools_unknown_name_raises(context):
    with pytest.raises(ValidationError):
        build_tools(["hello_world", "missing"], context)


def test_require_project(context):
    assert ToolContext(project_name="acme", git=context.git).require_project() == "acme"
    with pytest.raises(ValidationError, match="progetto"):
        context.require_project()
