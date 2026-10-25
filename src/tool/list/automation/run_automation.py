"""run_automation: queue a run of one of the project's automations and answer
at once with its id: the worker executes it, the result is in the Automation
tab. Which automations exist is list_automations' job: this tool only starts
one by name (an unknown name gets the available ones back). Only in a
chatbot's run of a project: never in an automation (no loops) or elsewhere."""
from typing import Annotated

from datapizza.tools import Tool, tool

from core.error import AppError
from models.domain.agent import RunOrigin
from models.domain.tool import RunAutomationResponse, ToolErrorResponse
from tool.context import ToolContext
from tool.spec import ToolSpec

AutomationName = Annotated[str, "Exact name of the automation to run, as list_automations gives it."]
AutomationInput = Annotated[str, "The text the automation receives as its input ('' = none)."]

_DESCRIPTION = (
    "Start one of the project's automations in the background and get its run id at once; "
    "it does not wait for the result (the user finds it in the Automation tab). "
    "Which automations exist: list_automations."
)


def build(context: ToolContext) -> Tool:

    @tool(name="run_automation", description=_DESCRIPTION)
    def run_automation(automation: AutomationName, input: AutomationInput) -> RunAutomationResponse | ToolErrorResponse:
        if not _can_launch(context):
            return ToolErrorResponse(error="Automation non disponibili in questa run: si lanciano solo dal chatbot "
                                           "di un progetto.")
        by_name = {pipeline.name: pipeline for pipeline in context.pipelines.runnable_pipelines(context.project_name)}
        if automation not in by_name:
            available = ", ".join(sorted(by_name)) or "nessuna"
            return ToolErrorResponse(error=f"Automation {automation!r} non disponibile. Disponibili: {available}.")
        try:
            run = context.pipelines.enqueue(by_name[automation].id, input)
        except AppError as exc:
            return ToolErrorResponse(error=str(exc))
        return RunAutomationResponse(automation=automation, run_id=run.id, status=run.status.value)

    return run_automation


def _can_launch(context: ToolContext) -> bool:
    """Only a chatbot's run of a project (an automation could start itself again)."""
    return chatbot_run(context)


def chatbot_run(context: ToolContext) -> bool:
    """The automation tools work only here: a chatbot's run of a project."""
    return context.pipelines is not None and context.project_name is not None and context.origin is RunOrigin.CHAT


RUN_AUTOMATION = ToolSpec(
    name="run_automation",
    description="Lancia un'automation del progetto in background e riporta l'id dell'esecuzione, senza aspettare il risultato.",
    build=build,
    chatbot_only=True,
)
