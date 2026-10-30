"""automation_status: how a run of one of the project's automations is going
(the one run_automation answered with): its status and its steps' statuses,
nothing else. No output nor error messages: they can be long or hold secrets
(the user reads them in the Automation tab). Only runs of the run's project,
and only in a chatbot's run (as run_automation)."""
from typing import Annotated

from datapizza.tools import Tool, tool

from core.error import AppError
from models.domain.tool import AutomationStatusResponse, AutomationStepStatus, ToolErrorResponse
from tool.context import ToolContext
from tool.list.automation.run_automation import chatbot_run
from tool.spec import ToolSpec

RunId = Annotated[int, "The run id that run_automation answered with."]

_DESCRIPTION = (
    "How a run of one of the project's automations is going: queued, running, done or failed, "
    "and the status of each step. Only statuses: the output is in the Automation tab. "
    "Use it when the user asks how an automation went."
)


def build(context: ToolContext) -> Tool:

    @tool(name="automation_status", description=_DESCRIPTION)
    def automation_status(run_id: RunId) -> AutomationStatusResponse | ToolErrorResponse:
        if not chatbot_run(context):
            return ToolErrorResponse(error="Stato delle automation disponibile solo nel chatbot di un progetto.")
        try:
            run = context.pipelines.get_run(run_id)
            pipeline = context.pipelines.get_pipeline(run.pipeline_id)
        except AppError:
            return _not_found(run_id)
        if pipeline.project_name != context.project_name:
            return _not_found(run_id)

        return AutomationStatusResponse(
            automation=pipeline.name,
            run_id=run_id,
            status=run.status.value,
            steps=[AutomationStepStatus(name=step.name, status=step.status.value) for step in run.steps],
        )

    return automation_status


def _not_found(run_id: int) -> ToolErrorResponse:
    return ToolErrorResponse(error=f"Esecuzione {run_id} non trovata tra quelle di questo progetto.")


AUTOMATION_STATUS = ToolSpec(
    name="automation_status",
    description="Stato di un'esecuzione di un'automation del progetto e dei suoi step (solo gli stati).",
    build=build,
    chatbot_only=True,
)
