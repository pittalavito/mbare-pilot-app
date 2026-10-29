"""list_agent_tasks: the project's agent tasks (Dati → Agent task), with their
status and the status of their latest Copilot session (when Copilot is there):
what delegate_task can delegate, and what the secretary reports on. Names and
titles only: the task's text is for Copilot, the chatbot does not need it.
Only in a chatbot's run."""
from datapizza.tools import Tool, tool

from core.error import AppError
from models.domain.tool import AgentTaskInfo, ListAgentTasksResponse, ToolErrorResponse
from tool.context import ToolContext
from tool.list.notes.todo_lists import notes_run
from tool.spec import ToolSpec

_DESCRIPTION = (
    "The project's agent tasks (name, title, status: todo, in_progress, done) with the status of their latest "
    "Copilot session: the ones delegate_task can delegate to Copilot. Use it to find the task the user means "
    "or to tell how the tasks are going."
)


def build(context: ToolContext) -> Tool:

    @tool(name="list_agent_tasks", description=_DESCRIPTION)
    def list_agent_tasks() -> ListAgentTasksResponse | ToolErrorResponse:
        if not notes_run(context):
            return ToolErrorResponse(error="Agent task disponibili solo nel chatbot di un progetto.")
        try:
            tasks = context.project_data.agent_tasks(context.project_name)
            sessions = context.copilot.sessions(context.project_name) if context.copilot else []
        except AppError as exc:
            return ToolErrorResponse(error=str(exc))
        latest: dict[str, str] = {}
        for session in sessions:  # newest first
            latest.setdefault(session.task_note, session.status.value)
        return ListAgentTasksResponse(tasks=[
            AgentTaskInfo(task=name, title=task.title, status=task.status.value, copilot_status=latest.get(name))
            for name, task in tasks
        ])

    return list_agent_tasks


LIST_AGENT_TASKS = ToolSpec(
    name="list_agent_tasks",
    description="Gli agent task del progetto con il loro stato e quello dell'ultima sessione Copilot.",
    build=build,
    chatbot_only=True,
)
