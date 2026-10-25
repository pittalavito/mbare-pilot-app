"""list_automations: the automations of the run's project that can be started
right now (active, with at least one step), with their descriptions. Only in a
chatbot's run, as run_automation."""
from datapizza.tools import Tool, tool

from models.domain.tool import AutomationInfo, ListAutomationsResponse, ToolErrorResponse
from tool.context import ToolContext
from tool.list.automation.run_automation import chatbot_run
from tool.spec import ToolSpec

_DESCRIPTION = (
    "The project's automations that can be started right now, with their descriptions: "
    "use it to choose which one to start with run_automation."
)


def build(context: ToolContext) -> Tool:

    @tool(name="list_automations", description=_DESCRIPTION)
    def list_automations() -> ListAutomationsResponse | ToolErrorResponse:
        if not chatbot_run(context):
            return ToolErrorResponse(error="Elenco delle automation disponibile solo nel chatbot di un progetto.")
        automations = context.pipelines.runnable_pipelines(context.project_name)
        return ListAutomationsResponse(automations=[
            AutomationInfo(name=pipeline.name, description=pipeline.description) for pipeline in automations
        ])

    return list_automations


LIST_AUTOMATIONS = ToolSpec(
    name="list_automations",
    description="Elenca le automation del progetto che si possono lanciare adesso, con la loro descrizione.",
    build=build,
    chatbot_only=True,
)
