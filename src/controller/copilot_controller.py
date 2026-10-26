"""Agent tasks delegated to GitHub Copilot CLI: sessions per project, the
planning chat (each message waits for Copilot's answer), the ok that queues
the execution for the worker, cancellation."""
from fastapi import APIRouter, Depends, Response, status

from controller.dependencies import copilot_service
from models.controller.copilot import (
    CopilotMessageRequest, CopilotMessageResponse, CopilotSessionRequest, CopilotSessionResponse, CopilotStatusResponse,
)
from service.copilot_service import CopilotService

router = APIRouter(tags=["copilot"])


@router.get("/copilot/status")
def copilot_status(project: str | None = None, service: CopilotService = Depends(copilot_service)) -> CopilotStatusResponse:
    """Whether Copilot CLI is installed, its version, and what is wrong with the
    coding-agent definition (the global one, plus ``project``'s when given)."""
    version = service.version()
    return CopilotStatusResponse(installed=version is not None, version=version, definition_error=service.coding_agent_error(project))


@router.get("/projects/{project}/copilot-sessions")
def list_sessions(project: str, service: CopilotService = Depends(copilot_service)) -> list[CopilotSessionResponse]:
    """Newest first."""
    return [CopilotSessionResponse.from_session(session) for session in service.sessions(project)]


@router.post("/projects/{project}/copilot-sessions", status_code=status.HTTP_201_CREATED)
def start_session(project: str, request: CopilotSessionRequest, service: CopilotService = Depends(copilot_service)) -> CopilotSessionResponse:
    """Delegate an agent task: the first planning turn runs now (Copilot reads the code and asks)."""
    return CopilotSessionResponse.from_session(service.start(project, request.task_note, request.repository))


@router.get("/copilot-sessions/{session_id}")
def get_session(session_id: int, service: CopilotService = Depends(copilot_service)) -> CopilotSessionResponse:
    return CopilotSessionResponse.from_session(service.session(session_id))


@router.get("/copilot-sessions/{session_id}/messages")
def list_messages(session_id: int, service: CopilotService = Depends(copilot_service)) -> list[CopilotMessageResponse]:
    """Oldest first."""
    return [CopilotMessageResponse.from_message(message) for message in service.messages(session_id)]


@router.post("/copilot-sessions/{session_id}/messages")
def send_message(session_id: int, request: CopilotMessageRequest, service: CopilotService = Depends(copilot_service)) -> CopilotSessionResponse:
    """A message of the planning chat; returns when Copilot has answered."""
    return CopilotSessionResponse.from_session(service.send(session_id, request.text))


@router.post("/copilot-sessions/{session_id}/approve")
def approve(session_id: int, service: CopilotService = Depends(copilot_service)) -> CopilotSessionResponse:
    """The ok: the execution goes in the worker's queue."""
    return CopilotSessionResponse.from_session(service.approve(session_id))


@router.post("/copilot-sessions/{session_id}/cancel")
def cancel(session_id: int, service: CopilotService = Depends(copilot_service)) -> CopilotSessionResponse:
    return CopilotSessionResponse.from_session(service.cancel(session_id))


@router.delete("/copilot-sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: int, service: CopilotService = Depends(copilot_service)) -> Response:
    """The session and its messages; the files Copilot changed stay."""
    service.delete(session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
