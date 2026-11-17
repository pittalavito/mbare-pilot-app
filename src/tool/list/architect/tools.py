"""The Architect's tools (the automation chatbot, blocco 05): what the
automation engine offers, the project's automations in YAML, the validation
of a proposal (the same rules as a save, nothing saved) and, after the
user's ok, the agent task for a missing tool. Saving a proposal is the
user's click in the chat, never a tool. Only in a chatbot's run of a project."""
from typing import Annotated

from datapizza.tools import Tool, tool

from core.error import AppError
from domain.pipeline import yaml_format
from domain.project.links import note_link
from models.domain.dev import PREPARE_AUTOMATION, VERIFY_AUTOMATION
from models.domain.note import AgentTask, ChecklistItem, TaskStatus, TaskType
from models.domain.pipeline import EdgeConditionKind, StepKind
from models.domain.tool import (
    AgentsResponse,
    AutomationValidationResponse,
    AutomationYamlResponse,
    ToolErrorResponse,
    ToolsResponse,
    ToolTaskResponse,
)
from tool.context import ToolContext
from tool.list.automation.run_automation import chatbot_run
from tool.spec import ToolSpec

_ONLY_IN_CHAT = "Disponibile solo nel chatbot di un progetto."
DEFAULT = "default"


def build_list_tools(context: ToolContext) -> Tool:

    @tool(name="list_tools", description=(
        "The tools a step of an automation can call (no LLM), with what they do and their args (name, type, default); "
        "a step writes «tool: <name>» with «args:»."
    ))
    def list_tools() -> ToolsResponse | ToolErrorResponse:
        if not chatbot_run(context):
            return ToolErrorResponse(error=_ONLY_IN_CHAT)
        lines = []
        for spec in context.require_pipelines().step_tools():
            properties, required = spec.schema()
            args = [f"{name} ({field.get('type', 'any')}{', obbligatorio' if name in required else f', default {field.get(DEFAULT)!r}'}): "
                    f"{field.get('description', '')}".strip() for name, field in properties.items()]
            lines.append(f"{spec.name} — {spec.description}" + (f"; args: {'; '.join(args)}" if args else "; nessun argomento"))
        return ToolsResponse(tools=lines)

    return list_tools


def build_list_agents(context: ToolContext) -> Tool:

    @tool(name="list_agents", description="The agents (Library and project) a step can use with «agent: <name>», with their descriptions.")
    def list_agents() -> AgentsResponse | ToolErrorResponse:
        if not chatbot_run(context):
            return ToolErrorResponse(error=_ONLY_IN_CHAT)
        agents = context.require_pipelines().usable_agents(context.require_project())
        return AgentsResponse(agents=[f"{agent.name} — {agent.description or '(senza descrizione)'}"
                                      + ("" if agent.project_name is None else " (del progetto)") for agent in agents])

    return list_agents


def build_read_automation(context: ToolContext) -> Tool:

    @tool(name="read_automation", description="One of the project's automations (name from list_automations), in YAML: read it before changing it.")
    def read_automation(name: Annotated[str, "The automation's name."]) -> AutomationYamlResponse | ToolErrorResponse:
        if not chatbot_run(context):
            return ToolErrorResponse(error=_ONLY_IN_CHAT)
        pipelines = context.require_pipelines()
        found = next((item for item in pipelines.list_pipelines(context.require_project()) if item.name.lower() == name.strip().lower()), None)
        if found is None:
            return ToolErrorResponse(error=f"Automation non trovata: {name}. Usa i nomi di list_automations.")
        return AutomationYamlResponse(name=found.name, yaml=yaml_format.dump(found))

    return read_automation


def build_validate_automation(context: ToolContext) -> Tool:

    @tool(name="validate_automation", description=(
        "Validate an automation written in YAML (the definitions' format: name, description, steps, edges) with the same "
        "rules as a save, without saving. Always validate before showing a proposal; fix the errors yourself."
    ))
    def validate_automation(yaml: Annotated[str, "The automation in YAML."]) -> AutomationValidationResponse | ToolErrorResponse:
        if not chatbot_run(context):
            return ToolErrorResponse(error=_ONLY_IN_CHAT)
        try:
            pipeline, current = context.require_pipelines().check_yaml(context.require_project(), yaml)
        except AppError as exc:
            return AutomationValidationResponse(valid=False, error=str(exc))
        return AutomationValidationResponse(
            valid=True, replaces=current is not None, system=pipeline.name in (PREPARE_AUTOMATION, VERIFY_AUTOMATION),
            steps=[f"{step.name}: {_step_kind(step)}" for step in pipeline.steps],
            edges=[f"{edge.source} → {edge.target}" + ("" if edge.condition is EdgeConditionKind.ALWAYS else f" ({edge.condition.value} {edge.value!r})")
                   for edge in pipeline.edges],
        )

    return validate_automation


def build_create_tool_task(context: ToolContext) -> Tool:

    @tool(name="create_tool_task", description=(
        "Only after the user said yes to your proposal: create the agent task «Sviluppo» to write a tool the automation needs "
        "and that does not exist. It is created in refinement; with an activity (name) it is linked to it."
    ))
    def create_tool_task(
        title: Annotated[str, "Short, e.g. «Tool git_tag: crea un tag»."],
        objective: Annotated[str, "What the tool must do: args, output text, when it fails."],
        criteria: Annotated[list[str], "Acceptance criteria, one per string."],
        activity: Annotated[str, "The activity to link it to (name); '' = none."] = "",
    ) -> ToolTaskResponse | ToolErrorResponse:
        if not chatbot_run(context) or context.project_data is None:
            return ToolErrorResponse(error=_ONLY_IN_CHAT)
        project, data = context.require_project(), context.project_data
        if not title.strip():
            return ToolErrorResponse(error="Serve un titolo.")
        try:
            parent = activity.strip() or None
            if parent is not None:
                data.activity(project, parent)  # exists, before creating the task
            name = data.create_agent_task(project, AgentTask(
                title=title.strip(), status=TaskStatus.REFINEMENT, type=TaskType.DEVELOPMENT, objective=objective.strip(),
                context="Tool per gli agenti e le automation (src/tool/list/), proposto dall'Architetto.",
                criteria=[ChecklistItem(text=text.strip()) for text in criteria if text.strip()],
            ))
            if parent is not None:
                data.link_agent_task(project, parent, name)
        except AppError as exc:
            return ToolErrorResponse(error=str(exc))
        return ToolTaskResponse(task=name, title=title.strip(), activity=parent, link=note_link(project, name))

    return create_tool_task


def _step_kind(step) -> str:
    if step.kind is StepKind.TOOL:
        return f"tool {step.tool_name}"
    if step.kind is StepKind.AGENT_CONFIG:
        return f"agente {step.agent_config_name}"
    return "agente proprio"


LIST_TOOLS = ToolSpec(name="list_tools", description="I tool che uno step di automation può chiamare, con descrizione e argomenti.",
                      build=build_list_tools, chatbot_only=True)
LIST_AGENTS = ToolSpec(name="list_agents", description="Gli agenti della Libreria e del progetto che uno step può usare.",
                       build=build_list_agents, chatbot_only=True)
READ_AUTOMATION = ToolSpec(name="read_automation", description="Un'automation del progetto in YAML.",
                           build=build_read_automation, chatbot_only=True)
VALIDATE_AUTOMATION = ToolSpec(name="validate_automation", description="Valida un'automation in YAML con le regole del salvataggio, senza salvare.",
                               build=build_validate_automation, chatbot_only=True)
CREATE_TOOL_TASK = ToolSpec(name="create_tool_task", description="Dopo il tuo ok: l'agent task per un tool che manca.",
                            build=build_create_tool_task, chatbot_only=True)
