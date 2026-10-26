"""list_agent_tasks: the project's agent tasks (Dati → Agent task), with their
status: what delegate_task can delegate. Names and titles only: the task's
text is for Copilot, the chatbot does not need it. Only in a chatbot's run."""
from datapizza.tools import Tool, tool

from core.error import AppError
from models.domain.tool import AgentTaskInfo, ListAgentTasksResponse, ToolErrorResponse
from tool.context import ToolContext
from tool.list.copilot.delegate_task import copilot_run
from tool.spec import ToolSpec

_DESCRIPTION = (
    "The project's agent tasks (name, title, status: todo, in_progress, done): the ones delegate_task can "
    "delegate to Copilot. Use it to find the task the user means."
)


def build(context: ToolContext) -> Tool:

    @tool(name="list_agent_tasks", description=_DESCRIPTION)
    def list_agent_tasks() -> ListAgentTasksResponse | ToolErrorResponse:
        if not copilot_run(context) or context.project_data is None:
            return ToolErrorResponse(error="Agent task disponibili solo nel chatbot di un progetto.")
        try:
            tasks = context.project_data.agent_tasks(context.project_name)
        except AppError as exc:
            return ToolErrorResponse(error=str(exc))
        return ListAgentTasksResponse(
            tasks=[AgentTaskInfo(task=name, title=task.title, status=task.status.value) for name, task in tasks],
        )

    return list_agent_tasks


LIST_AGENT_TASKS = ToolSpec(
    name="list_agent_tasks",
    description="Gli agent task del progetto con il loro stato: quelli che si possono delegare a Copilot.",
    build=build,
    chatbot_only=True,
)
