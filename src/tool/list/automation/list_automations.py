"""list_automations: the automations of the run's project, with their
descriptions, whether they are active and how many steps they have (the
Architect reads them; the ones active with steps are those run_automation can
start). Only in a chatbot's run, as run_automation."""
from datapizza.tools import Tool, tool

from models.domain.tool import AutomationInfo, ListAutomationsResponse, ToolErrorResponse
from tool.context import ToolContext
from tool.list.automation.run_automation import chatbot_run
from tool.spec import ToolSpec

_DESCRIPTION = (
    "The project's automations with their descriptions, whether they are active and how many steps they have "
    "(only the active ones with steps can be started)."
)


def build(context: ToolContext) -> Tool:

    @tool(name="list_automations", description=_DESCRIPTION)
    def list_automations() -> ListAutomationsResponse | ToolErrorResponse:
        if not chatbot_run(context):
            return ToolErrorResponse(error="Elenco delle automation disponibile solo nel chatbot di un progetto.")
        automations = context.require_pipelines().list_pipelines(context.require_project())
        return ListAutomationsResponse(automations=[
            AutomationInfo(name=pipeline.name, description=pipeline.description, active=pipeline.active, steps=len(pipeline.steps))
            for pipeline in automations
        ])

    return list_automations


LIST_AUTOMATIONS = ToolSpec(
    name="list_automations",
    description="Elenca le automation del progetto, con descrizione, se sono attive e quanti step hanno.",
    build=build,
    chatbot_only=True,
)
