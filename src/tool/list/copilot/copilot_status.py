"""copilot_status: how a task delegated to Copilot is going (the session
delegate_task answered with): its status, how many files changed and whether
HEAD moved. Nothing else: Copilot's messages and the changes are in its chat.
Only sessions of the run's project, only in a chatbot's run."""
from typing import Annotated

from datapizza.tools import Tool, tool

from core.error import AppError
from models.domain.tool import CopilotStatusResponse, ToolErrorResponse
from tool.context import ToolContext
from tool.list.copilot.delegate_task import chat_link, copilot_run
from tool.spec import ToolSpec

SessionId = Annotated[int, "The session id that delegate_task answered with."]

_DESCRIPTION = (
    "How a task delegated to Copilot is going: planning (its chat waits for the user's ok; copilot_answering while "
    "Copilot is still writing there), queued, running, done, "
    "failed or cancelled, with the number of changed files. Only statuses: the details are in the Copilot chat. "
    "Use it when the user asks how a delegated task went."
)


def build(context: ToolContext) -> Tool:

    @tool(name="copilot_status", description=_DESCRIPTION)
    def copilot_status(session_id: SessionId) -> CopilotStatusResponse | ToolErrorResponse:
        if not copilot_run(context):
            return ToolErrorResponse(error="Stato di Copilot disponibile solo nel chatbot di un progetto.")
        try:
            session = context.require_copilot().session(session_id)
        except AppError:
            return _not_found(session_id)
        if session.project_name != context.project_name:
            return _not_found(session_id)
        return CopilotStatusResponse(
            session_id=session_id,
            task=session.task_note,
            status=session.status.value,
            copilot_answering=session.planning_turn is not None,
            changed_files=len(session.changed_files),
            head_moved=session.head_moved,
            chat=chat_link(session.project_name, session_id),
        )

    return copilot_status


def _not_found(session_id: int) -> ToolErrorResponse:
    return ToolErrorResponse(error=f"Sessione Copilot {session_id} non trovata tra quelle di questo progetto.")


COPILOT_STATUS = ToolSpec(
    name="copilot_status",
    description="Stato di un task delegato a Copilot (solo lo stato e quanti file ha cambiato).",
    build=build,
    chatbot_only=True,
)
