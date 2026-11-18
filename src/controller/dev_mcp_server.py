"""The app's MCP server for **Claude Code** (plan 20), mounted in the API at
``/mcp-dev``: the requests of tools the Architetto wrote, for Claude Code on the
user's PC working on a clone of mbare-pilot-app (it writes the tool, opens the
PR, marks the request done). Separate from Copilot's server (``/mcp``).

Every call carries the token generated in Admin → «Richieste di tool»
(``Authorization: Bearer <token>``); a wrong or missing one is refused. The
logic is in ToolRequestService; here only the tools and the token."""
from collections.abc import Callable
from typing import TYPE_CHECKING, Annotated

from mcp.server.mcpserver import Context, MCPServer
from pydantic import Field

from controller.mcp_server import _reported, _token
from models.domain.tool_request import ToolRequest, ToolRequestDetail, ToolRequestStatus

if TYPE_CHECKING:
    from service.tool_request_service import ToolRequestService

_INSTRUCTIONS = (
    "Requests of tools for the code of mbare-pilot-app (the tools agents and automations call, src/tool/list/). "
    "List them, read one, write the tool with its tests in the repository, open the PR, then mark the request done "
    "with the PR's link (or dismissed, saying why)."
)
DEV_MCP_TOOLS: dict[str, str] = {
    "list_tool_requests": "The requests of tools still open or being worked, newest first.",
    "read_tool_request": "One request: title, objective, acceptance criteria, where it was asked and, if any, the YAML of the "
        "automation that needs the tool.",
    "update_tool_request": "Mark a request: working (you are on it), done (with the PR's link), dismissed (with the reason), "
        "open (again).",
}


def build_dev_mcp_server(requests: Callable[[], "ToolRequestService"]) -> MCPServer:
    """The server and its tools; ``requests`` gives the service at call time (the Container is built at startup)."""
    server = MCPServer("mbare-pilot-dev", instructions=_INSTRUCTIONS)

    def service(ctx: Context) -> "ToolRequestService":
        current = requests()
        current.check_token(_token(ctx))
        return current

    @server.tool(description=DEV_MCP_TOOLS["list_tool_requests"])
    @_reported
    def list_tool_requests(ctx: Context) -> list[ToolRequest]:
        return service(ctx).list_requests(only_open=True)

    @server.tool(description=DEV_MCP_TOOLS["read_tool_request"])
    @_reported
    def read_tool_request(request: Annotated[int, Field(description="The request's number.")], ctx: Context) -> ToolRequestDetail:
        current = service(ctx)
        found = current.get(request)
        return ToolRequestDetail(**found.model_dump(), automation_yaml=current.automation_yaml(found))

    @server.tool(description=DEV_MCP_TOOLS["update_tool_request"])
    @_reported
    def update_tool_request(
        request: Annotated[int, Field(description="The request's number.")],
        status: Annotated[ToolRequestStatus, Field(description="open, working, done or dismissed.")],
        ctx: Context,
        pr_url: Annotated[str, Field(description="With done: the PR's link.")] = "",
        reason: Annotated[str, Field(description="With dismissed: why.")] = "",
    ) -> ToolRequest:
        return service(ctx).update(request, status, pr_url, reason)

    return server
