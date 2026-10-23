"""Tool registry: one ``ToolSpec`` per tool implemented in code, keyed by name.

Tools sit above the services: a tool file under tool/list/ exposes a spec whose
builder receives the run's ``ToolContext`` (services + project) and returns the
datapizza ``Tool``, closing over what it needs. Tools without dependencies are
registered as they are with ``static``. At startup the registry (name +
description) is synced into the DB tool catalog, from which agent
configurations pick their tools by name; AgentService builds the chosen ones
for every run with ``build_tools``.
"""
import copy

from datapizza.tools import Tool

from core.error import ValidationError
from tool.context import ToolContext
from tool.list.agent.ask_agent import ASK_AGENT
from tool.list.automation.run_automation import RUN_AUTOMATION
from tool.list.git.git_pull_fast_forward import GIT_PULL_FAST_FORWARD
from tool.list.git.git_stash import GIT_STASH
from tool.list.git.git_stash_apply import GIT_STASH_APPLY
from tool.list.git.git_status import GIT_STATUS
from tool.list.hello_world import hello_world
from tool.spec import ToolSpec, static

TOOL_REGISTRY: dict[str, ToolSpec] = {
    spec.name: spec
    for spec in (
        static(hello_world),
        ASK_AGENT,
        RUN_AUTOMATION,
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
    tools = [TOOL_REGISTRY[name].build(context) for name in names]
    return [_masked(tool, context) for tool in tools] if context.mask else tools


def _masked(tool: Tool, context: ToolContext) -> Tool:
    """A copy of ``tool`` (static tools are shared) whose arguments arrive
    unmasked and whose output leaves masked: the tool works on real values,
    the LLM only sees aliases."""
    original = tool.func
    mask = context.mask

    def run(*args, **kwargs):
        result = original(*mask.unmask_value(args), **mask.unmask_value(kwargs))
        return mask.mask(result) if isinstance(result, str) else result

    masked = copy.copy(tool)
    masked.func = run
    return masked
