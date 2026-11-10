"""The app's MCP server for GitHub Copilot, mounted in the API at ``/mcp``
(streamable HTTP, stateless, JSON answers): while Copilot works on an agent
task it reads the task and its references, asks the user, says it is done.

Every call carries the token of one Copilot session (``Authorization: Bearer
<token>``, written by the app in the CLI's MCP configuration): the tools see
only that session's task. The logic is in CopilotService (``mcp_*``,
``ask_user``, ``finish``); here only the tools' names, descriptions and the
token. No masking: Copilot already reads the code in clear.

Sync tools run in a worker thread (the SDK's ``to_thread``): ``ask_user`` can
wait minutes without blocking the server, and a planning turn (which runs
inside an API request) can call back into the API."""
from collections.abc import Callable
from functools import wraps
from typing import TYPE_CHECKING, Annotated

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field
from starlette.applications import Starlette

from core.error import AppError
from models.domain.note import TaskLink

if TYPE_CHECKING:
    from service.copilot_service import CopilotService

_INSTRUCTIONS = (
    "Server dell'app mbare-pilot per l'agent task che ti è stato affidato. read_task: il task completo; list_references e "
    "read_reference: i riferimenti collegati; ask_user: una domanda all'utente durante l'esecuzione (aspetta la risposta); "
    "finish: quando hai finito, con un riassunto."
)


def _token(ctx: Context) -> str:
    """The bearer token of the HTTP request; ``""`` without one."""
    request = ctx.request_context.request
    header = request.headers.get("authorization", "") if request is not None else ""
    return header.removeprefix("Bearer ").strip() if header.startswith("Bearer ") else ""


def _reported[**P, R](tool: Callable[P, R]) -> Callable[P, R]:
    """The app's errors (an unknown token, a reference not linked...) reach Copilot with their message."""
    @wraps(tool)
    def call(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return tool(*args, **kwargs)
        except AppError as exc:
            raise ToolError(str(exc)) from exc
    return call


def build_mcp_server(copilot: Callable[[], "CopilotService"]) -> MCPServer:
    """The server and its tools; ``copilot`` gives the service at call time (the Container is built at startup)."""
    server = MCPServer("mbare-pilot", instructions=_INSTRUCTIONS)

    @server.tool(description="The agent task you work on: title, type, objective, context, acceptance criteria, constraints, and the "
                             "checklist of what a task of its type should have.")
    @_reported
    def read_task(ctx: Context) -> dict:
        return copilot().mcp_task(_token(ctx))

    @server.tool(description="What the task links: references (code, context), notes and uploaded files, by name with a title. "
                             "found=false: it no longer exists.")
    @_reported
    def list_references(ctx: Context) -> list[TaskLink]:
        return copilot().mcp_links(_token(ctx))

    @server.tool(description="The content of one of the task's references, notes or files, by the name list_references gives.")
    @_reported
    def read_reference(name: Annotated[str, Field(description="The name, as list_references gives it.")], ctx: Context) -> str:
        return copilot().mcp_link(_token(ctx), name)

    @server.tool(description="During the execution: ask the user something you cannot decide alone. The question appears in the "
                             "app's chat and this waits for the answer (minutes); without an answer in time, decide yourself and "
                             "say so in finish. While planning, ask in your answer instead.")
    @_reported
    def ask_user(question: Annotated[str, Field(description="One clear question.")], ctx: Context) -> str:
        return copilot().ask_user(_token(ctx), question)

    @server.tool(description="Call it when you have finished the task: a short summary of what you changed (files and why) and "
                             "whether the acceptance criteria are met. The user then checks your work.")
    @_reported
    def finish(summary: Annotated[str, Field(description="What you did, briefly.")], ctx: Context) -> str:
        return copilot().finish(_token(ctx), summary)

    return server


def mcp_app(server: MCPServer) -> Starlette:
    """The ASGI app to mount: stateless (no MCP session to keep between
    calls), JSON answers. Every tool needs the session's token, so the DNS
    rebinding check (on the Host header) is off: the API answers on whatever
    host API_URL says."""
    return server.streamable_http_app(
        streamable_http_path="/", stateless_http=True, json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
