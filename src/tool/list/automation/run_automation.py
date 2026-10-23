"""run_automation: queue a run of one of the project's automations and answer
at once with its id: the worker executes it, the result is in the Automation
tab. The automations the model can pick, with their descriptions, are written
into the tool description when the tool is built for a run. Not available to
agents running inside an automation (no loops) or asked by another agent."""
from typing import Annotated

from datapizza.tools import Tool, tool

from core.error import AppError
from models.domain.agent import RunOrigin
from models.domain.tool import RunAutomationResponse, ToolErrorResponse
from tool.context import ToolContext
from tool.spec import ToolSpec

AutomationName = Annotated[str, "Exact name of the automation to run, from the list in this tool's description."]
AutomationInput = Annotated[str, "The text the automation receives as its input ('' = none)."]

_DESCRIPTION = (
    "Start one of the project's automations in the background and get its run id at once; "
    "it does not wait for the result (the user finds it in the Automation tab)."
)


def build(context: ToolContext) -> Tool:
    automations = context.pipelines.runnable_pipelines(context.project_name) if _can_launch(context) else []
    listing = "\n".join(f"- {pipeline.name}: {pipeline.description or '(no description)'}" for pipeline in automations)
    description = f"{_DESCRIPTION}\nAvailable automations:\n{listing or '- none'}"

    @tool(name="run_automation", description=description)
    def run_automation(automation: AutomationName, input: AutomationInput) -> str:
        if not _can_launch(context):
            return ToolErrorResponse(error="Automation non disponibili in questa run: si lanciano solo da un agente "
                                           "di un progetto chiamato dall'utente.").model_dump_json()
        by_name = {pipeline.name: pipeline for pipeline in automations}
        if automation not in by_name:
            available = ", ".join(sorted(by_name)) or "nessuna"
            return ToolErrorResponse(error=f"Automation {automation!r} non disponibile. Disponibili: {available}.").model_dump_json()
        try:
            run = context.pipelines.enqueue(by_name[automation].id, input)
        except AppError as exc:
            return ToolErrorResponse(error=str(exc)).model_dump_json()
        return RunAutomationResponse(automation=automation, run_id=run.id, status=run.status.value).model_dump_json()

    return run_automation


def _can_launch(context: ToolContext) -> bool:
    """Only a run of a project, asked by the user: never from inside an
    automation (it could start itself again) nor from a delegated agent."""
    return (
        context.pipelines is not None and context.project_name is not None
        and context.origin is not RunOrigin.PIPELINE and context.depth == 0
    )


RUN_AUTOMATION = ToolSpec(
    name="run_automation",
    description="Lancia un'automation del progetto in background e riporta l'id dell'esecuzione, senza aspettare il risultato.",
    build=build,
)
