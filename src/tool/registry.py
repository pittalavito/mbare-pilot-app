"""Tool registry: one ``ToolSpec`` per tool implemented in code, keyed by name.

Tools sit above the services: a tool file under tool/list/ exposes a spec whose
builder receives the run's ``ToolContext`` (services + project) and returns the
datapizza ``Tool``, closing over what it needs. Tools without dependencies are
registered as they are with ``static``. At startup the registry (name +
description) is synced into the DB tool catalog, from which agent
configurations pick their tools by name; AgentService builds the chosen ones
for every run with ``build_tools``; AgentMask wraps them (masking).
"""
from datapizza.tools import Tool

from core.error import ValidationError
from tool.context import ToolContext
from tool.list.automation.automation_status import AUTOMATION_STATUS
from tool.list.automation.list_automations import LIST_AUTOMATIONS
from tool.list.automation.run_automation import RUN_AUTOMATION
from tool.list.copilot.copilot_status import COPILOT_STATUS
from tool.list.copilot.delegate_task import DELEGATE_TASK
from tool.list.copilot.list_agent_tasks import LIST_AGENT_TASKS
from tool.list.git.git_pull_fast_forward import GIT_PULL_FAST_FORWARD
from tool.list.git.git_stash import GIT_STASH
from tool.list.git.git_stash_apply import GIT_STASH_APPLY
from tool.list.git.git_status import GIT_STATUS
from tool.list.hello_world import hello_world
from tool.list.notes.todo_lists import CREATE_TODO_LIST, LIST_TODO_LISTS, READ_TODO_LIST, UPDATE_TODO_LIST
from tool.list.project.read_context import READ_CONTEXT
from tool.spec import ToolSpec, static

TOOL_REGISTRY: dict[str, ToolSpec] = {
    spec.name: spec
    for spec in (
        static(hello_world),
        LIST_AUTOMATIONS,
        RUN_AUTOMATION,
        AUTOMATION_STATUS,
        LIST_TODO_LISTS,
        READ_TODO_LIST,
        CREATE_TODO_LIST,
        UPDATE_TODO_LIST,
        LIST_AGENT_TASKS,
        DELEGATE_TASK,
        COPILOT_STATUS,
        READ_CONTEXT,
        GIT_STATUS,
        GIT_PULL_FAST_FORWARD,
        GIT_STASH,
        GIT_STASH_APPLY,
    )
}
"""Every tool implemented in code, keyed by name."""


def build_tools(names: list[str], context: ToolContext) -> list[Tool]:
    """The tools ``names`` built for one run, in order. Raises ValidationError
    when a name has no implementation (e.g. a catalogued tool removed from code)."""
    missing = [name for name in names if name not in TOOL_REGISTRY]
    if missing:
        raise ValidationError(f"Tool non implementati nel codice: {', '.join(missing)}")
    return [TOOL_REGISTRY[name].build(context) for name in names]
