"""read_context: the project's context for its chatbot, the markdown files in
``<MBARE_PILOT_HOME>/projects/<slug>/chat-bot/`` (not its system prompt).
Meant as a last resort: it costs tokens only when called."""
from datapizza.tools import Tool, tool

from core.error import AppError
from models.domain.tool import ReadContextResponse, ToolErrorResponse
from tool.context import ToolContext
from tool.spec import ToolSpec


def build(context: ToolContext) -> Tool:

    @tool(name="read_context", description= "Last resort: the project's context (domain, stack, sources). Use it only when the request is ambiguous or no automation seems to fit.")
    def read_context() -> str:
        if context.project_data is None or context.project_name is None:
            return ToolErrorResponse(error="Contesto non disponibile fuori da un progetto.").model_dump_json()
        try:
            files = context.project_data.chatbot_context(context.project_name)
        except AppError as exc:
            return ToolErrorResponse(error=str(exc)).model_dump_json()
        if not files:
            return ToolErrorResponse(error="Il progetto non ha file di contesto per il chatbot.").model_dump_json()
        return ReadContextResponse(files=files).model_dump_json()

    return read_context


READ_CONTEXT = ToolSpec(
    name="read_context",
    description="Legge il contesto del progetto per il chatbot (i .md della cartella chat-bot), come ultima risorsa.",
    build=build,
)
