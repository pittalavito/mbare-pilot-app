import pytest

from core.error import ValidationError
from tool.context import ToolContext
from tool.registry import TOOL_REGISTRY, build_tools


@pytest.fixture
def context(git_service):
    return ToolContext(project_name=None, git=git_service)


def test_registry_is_keyed_by_tool_name():
    assert all(name == spec.name for name, spec in TOOL_REGISTRY.items())


def test_every_spec_builds_a_tool_with_its_name_and_a_description(context):
    for name, spec in TOOL_REGISTRY.items():
        assert spec.description
        assert spec.build(context).name == name


def test_only_the_automation_copilot_and_notes_tools_are_for_chatbots_and_the_catalog_says_so(agent_config_service):
    assert {name for name, spec in TOOL_REGISTRY.items() if spec.chatbot_only} == {
        "list_automations", "run_automation", "automation_status", "list_agent_tasks", "delegate_task", "copilot_status",
        "list_todo_lists", "read_todo_list", "create_todo_list", "update_todo_list",
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


@pytest.mark.parametrize("require, field", [
    ("require_pipelines", "pipelines"), ("require_project_data", "project_data"), ("require_copilot", "copilot"),
])
def test_require_service(context, require, field):
    service = object()
    assert getattr(ToolContext(project_name="acme", git=context.git, **{field: service}), require)() is service
    with pytest.raises(ValidationError, match="non ha accesso"):
        getattr(context, require)()
