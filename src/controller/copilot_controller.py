"""Agent tasks delegated to GitHub Copilot CLI: sessions per project, the
planning chat (each message is queued for the worker, which saves Copilot's
answer: the page polls), the ok that queues the execution for the worker,
cancellation; what the turns used, per session
and for Observability (/observability/copilot/...)."""
from fastapi import APIRouter, Depends, Response, status

from controller.dependencies import copilot_service
from models.controller.copilot import (
    CopilotDeletedResponse,
    CopilotMessageRequest,
    CopilotMessageResponse,
    CopilotModelOptionResponse,
    CopilotModelUsageResponse,
    CopilotSessionRequest,
    CopilotSessionResponse,
    CopilotSessionUsageResponse,
    CopilotStatusResponse,
    CopilotTurnResponse,
)
from service.copilot_service import CopilotService

router = APIRouter(tags=["copilot"])


@router.get("/copilot/status")
def copilot_status(project: str | None = None, service: CopilotService = Depends(copilot_service)) -> CopilotStatusResponse:
    """Whether Copilot CLI is installed, its version, the prompts and models to
    choose from when delegating, and what is wrong with the coding-agent
    definition (the global one, plus ``project``'s when given)."""
    version = service.version()
    settings, error = service.coding_agent_or_error(project)
    return CopilotStatusResponse(
        installed=version is not None, version=version, definition_error=error, default_model=service.default_model,
        prompts=list(settings.prompts) if settings else [],
        models=[CopilotModelOptionResponse.from_option(model, usage) for model, usage in service.model_options(settings)] if settings else [],
    )


@router.get("/projects/{project}/copilot-sessions")
def list_sessions(project: str, service: CopilotService = Depends(copilot_service)) -> list[CopilotSessionResponse]:
    """Newest first."""
    return [CopilotSessionResponse.from_session(session) for session in service.sessions(project)]


@router.post("/projects/{project}/copilot-sessions", status_code=status.HTTP_201_CREATED)
def start_session(project: str, request: CopilotSessionRequest, service: CopilotService = Depends(copilot_service)) -> CopilotSessionResponse:
    """Delegate an agent task: returns at once, with the first planning turn queued for the worker
    (Copilot reads the code and asks; its answer arrives in the messages)."""
    return CopilotSessionResponse.from_session(service.start(project, request.task_note, request.repositories, request.prompt, request.model))


@router.delete("/projects/{project}/copilot-sessions")
def delete_task_sessions(project: str, task_note: str, service: CopilotService = Depends(copilot_service)) -> CopilotDeletedResponse:
    """Every session of an agent task, with their messages (409 if one is queued or running); the files Copilot changed stay."""
    return CopilotDeletedResponse(deleted=service.delete_task_sessions(project, task_note))


@router.get("/copilot-sessions/{session_id}")
def get_session(session_id: int, service: CopilotService = Depends(copilot_service)) -> CopilotSessionResponse:
    return CopilotSessionResponse.from_session(service.session(session_id))


@router.get("/copilot-sessions/{session_id}/messages")
def list_messages(session_id: int, service: CopilotService = Depends(copilot_service)) -> list[CopilotMessageResponse]:
    """Oldest first."""
    return [CopilotMessageResponse.from_message(message) for message in service.messages(session_id)]


@router.get("/copilot-sessions/{session_id}/turns")
def session_usage(session_id: int, service: CopilotService = Depends(copilot_service)) -> CopilotSessionUsageResponse:
    """What each turn used (AI credits, tokens), oldest first, and the sum."""
    return CopilotSessionUsageResponse.from_turns(service.session_turns(session_id))


@router.get("/observability/copilot/turns")
def recent_turns(limit: int = 100, project: str | None = None, service: CopilotService = Depends(copilot_service)) -> list[CopilotTurnResponse]:
    """Every session's turns, newest first (deleted sessions too)."""
    return [CopilotTurnResponse.from_turn(turn) for turn in service.recent_turns(limit, project)]


@router.get("/observability/copilot/models")
def usage_by_model(days: int | None = None, project: str | None = None, service: CopilotService = Depends(copilot_service)) -> list[CopilotModelUsageResponse]:
    """Totals per model over the last ``days`` (omitted = ever), the most AI credits first."""
    return [CopilotModelUsageResponse.from_model_usage(item) for item in service.usage_by_model(days, project)]


@router.post("/copilot-sessions/{session_id}/messages")
def send_message(session_id: int, request: CopilotMessageRequest, service: CopilotService = Depends(copilot_service)) -> CopilotSessionResponse:
    """A message of the planning chat: returns at once, the worker runs the turn (409 while the previous one is pending)."""
    return CopilotSessionResponse.from_session(service.send(session_id, request.text))


@router.post("/copilot-sessions/{session_id}/approve")
def approve(session_id: int, service: CopilotService = Depends(copilot_service)) -> CopilotSessionResponse:
    """The ok: the execution goes in the worker's queue."""
    return CopilotSessionResponse.from_session(service.approve(session_id))


@router.post("/copilot-sessions/{session_id}/cancel")
def cancel(session_id: int, service: CopilotService = Depends(copilot_service)) -> CopilotSessionResponse:
    """Stops the execution, or Copilot's pending answer in the planning chat (the chat stays open)."""
    return CopilotSessionResponse.from_session(service.cancel(session_id))


@router.delete("/copilot-sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: int, service: CopilotService = Depends(copilot_service)) -> Response:
    """The session and its messages; the files Copilot changed stay."""
    service.delete(session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
