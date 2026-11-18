"""The Architect's tools (the automation chatbot, blocco 05): what the
automation engine offers, the project's automations in YAML, the validation
of a proposal (the same rules as a save, nothing saved) and, after the
user's ok, the agent task for a missing tool. Saving a proposal is the
user's click in the chat, never a tool. Only in a chatbot's run of a project."""
from typing import Annotated

from datapizza.tools import Tool, tool

from core.error import AppError
from domain.pipeline import yaml_format
from models.domain.agent import RunOrigin
from models.domain.pipeline import EdgeConditionKind, StepKind
from models.domain.tool import (
    AgentsResponse,
    AutomationValidationResponse,
    AutomationYamlResponse,
    ToolErrorResponse,
    ToolRequestResponse,
    ToolsResponse,
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
            valid=True, replaces=current is not None,
            steps=[f"{step.name}: {_step_kind(step)}" for step in pipeline.steps],
            edges=[f"{edge.source} → {edge.target}" + ("" if edge.condition is EdgeConditionKind.ALWAYS else f" ({edge.condition.value} {edge.value!r})")
                   for edge in pipeline.edges],
        )

    return validate_automation


def build_request_tool(context: ToolContext) -> Tool:

    @tool(name="request_tool", description=(
        "Only after the user said yes to your proposal: ask for a tool the automation needs and that does not exist. "
        "The request goes to the developers of the app (Claude Code, on the app's own code), not to the project: "
        "it is of the whole app. Give the automation's name if there is one."
    ))
    def request_tool(
        title: Annotated[str, "Short, e.g. «Tool git_tag: crea un tag»."],
        objective: Annotated[str, "What the tool must do: args, output text, when it fails."],
        criteria: Annotated[list[str], "Acceptance criteria, one per string."],
        automation: Annotated[str, "The automation that needs it (name); '' = none."] = "",
        activity: Annotated[str, "The activity it comes from (name); '' = none."] = "",
    ) -> ToolRequestResponse | ToolErrorResponse:
        if context.origin is not RunOrigin.CHAT or context.project_name is None or context.tool_requests is None:
            return ToolErrorResponse(error=_ONLY_IN_CHAT)
        project = context.require_project()
        try:
            request = context.tool_requests.create(project, title, objective, criteria, automation, activity)
        except AppError as exc:
            return ToolErrorResponse(error=str(exc))
        return ToolRequestResponse(request=request.id or 0, title=request.title, link=f"/admin?tab=tool-requests&request={request.id}")

    return request_tool


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
REQUEST_TOOL = ToolSpec(name="request_tool", description="Dopo il tuo ok: la richiesta di un tool che manca, per Claude Code sul codice dell'app.",
                        build=build_request_tool, chatbot_only=True)
