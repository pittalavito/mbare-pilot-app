"""Admin → «Richieste di tool»: the requests of tools the Architetto
wrote for Claude Code, the token of Claude Code's MCP server (with the command
to add it) and dismissing a request by hand."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from config import Config
from controller.dependencies import tool_request_service
from models.domain.tool_request import ToolRequest, ToolRequestStatus
from service.tool_request_service import ToolRequestService

router = APIRouter(prefix="/admin/tool-requests", tags=["tool-requests"])


class ToolRequestsResponse(BaseModel):
    requests: list[ToolRequest]
    has_token: bool
    url: str
    """Where Claude Code reaches the MCP server."""


class TokenResponse(BaseModel):
    token: str
    """Shown once: only its hash is kept."""
    url: str
    command: str
    """The command to add the server to Claude Code."""


class DismissRequest(BaseModel):
    reason: str


def dev_mcp_url() -> str:
    """Where Claude Code reaches the server: the API is under /api, the server under /mcp-dev."""
    return f"{Config.get().api_url.rstrip('/')}/api/mcp-dev/"


@router.get("")
def list_tool_requests(service: ToolRequestService = Depends(tool_request_service)) -> ToolRequestsResponse:
    return ToolRequestsResponse(requests=service.list_requests(), has_token=service.has_token(), url=dev_mcp_url())


@router.post("/token")
def new_token(service: ToolRequestService = Depends(tool_request_service)) -> TokenResponse:
    """A new token (the old one stops working) and the command for Claude Code."""
    token, url = service.new_token(), dev_mcp_url()
    return TokenResponse(token=token, url=url,
                         command=f'claude mcp add --transport http mbare-pilot-dev {url} --header "Authorization: Bearer {token}"')


@router.post("/{request_id}/dismiss")
def dismiss(request_id: int, request: DismissRequest, service: ToolRequestService = Depends(tool_request_service)) -> ToolRequest:
    """400 without a reason, 404 for an unknown request."""
    return service.update(request_id, ToolRequestStatus.DISMISSED, reason=request.reason)
