"""delegate_task: delegate one of the project's agent tasks to GitHub Copilot
on a repository of the project. It opens the planning chat and returns at
once: the worker runs Copilot, which reads the code and answers with its
questions (or a plan) in the app's Copilot chat, a minute or so later; nothing
changes until the user presses «Ok, parti» there. The chatbot asks the user to
confirm task and repository before calling it.

Copilot's answer stays in its chat (it can quote code): the tool returns only
the session and the link. Only in a chatbot's run of a project."""
from typing import Annotated
from urllib.parse import quote

from datapizza.tools import Tool, tool

from core.error import AppError
from models.domain.agent import RunOrigin
from models.domain.tool import DelegateTaskResponse, ToolErrorResponse
from tool.context import ToolContext
from tool.list.git.errors import git_error
from tool.list.git.params import Repository
from tool.spec import ToolSpec

Task = Annotated[str, "The agent task's note name, as list_agent_tasks gives it (agent-task-<title>.md)."]

_DESCRIPTION = (
    "Delegate one of the project's agent tasks to GitHub Copilot on a repository: it opens a chat where Copilot "
    "reads the code and asks its questions; it returns at once, Copilot answers in that chat shortly after (the "
    "worker must be running), so do not wait for it nor report what Copilot said. Copilot changes nothing until the "
    "user gives the ok in that chat, and it never commits. BEFORE calling it, tell the user which task and repository you would delegate and wait for an "
    "explicit yes in their next message. Which tasks exist: list_agent_tasks. Give the user the chat link."
)


def build(context: ToolContext) -> Tool:

    @tool(name="delegate_task", description=_DESCRIPTION)
    def delegate_task(task: Task, repository: Repository) -> DelegateTaskResponse | ToolErrorResponse:
        if not copilot_run(context):
            return ToolErrorResponse(error="Delega a Copilot disponibile solo nel chatbot di un progetto.")
        copilot, project_name = context.require_copilot(), context.require_project()
        try:
            session = copilot.start(project_name, task, repository)
        except AppError as exc:
            return git_error(context, exc)
        return DelegateTaskResponse(
            session_id=session.id,
            task=task,
            repository=repository,
            chat=chat_link(project_name, session.id),
            next_step=(
                "Apri la chat di Copilot: tra poco ci trovi le sue domande (le scrive il worker, che deve essere acceso). "
                "Rispondi e premi «Ok, parti» quando il piano ti va bene."
            ),
        )

    return delegate_task


def copilot_run(context: ToolContext) -> bool:
    """The Copilot tools work only here: a chatbot's run of a project."""
    return context.copilot is not None and context.project_name is not None and context.origin is RunOrigin.CHAT


def chat_link(project_name: str, session_id: int) -> str:
    """The session's chat in the app (Copilot tab of the project)."""
    return f"/projects/{quote(project_name)}/copilot?session={session_id}"


DELEGATE_TASK = ToolSpec(
    name="delegate_task",
    description=(
        "Delega un agent task a GitHub Copilot su un repository: apre la chat in cui Copilot fa le sue domande; "
        "parte solo con l'ok dell'utente e non fa commit."
    ),
    build=build,
    chatbot_only=True,
)
