"""create_code_reference: the refiner's tool. Scans the project's code for the
``todoMbarePilot{description}`` comments and writes them as one code
reference (service/code_todo_service.py). The agent never sees the comments
nor the code: it gets the counts and the link to the note, which the user
opens and edits. Only in a chatbot's run of a project."""
from urllib.parse import quote

from datapizza.tools import Tool, tool

from core.error import AppError
from models.domain.agent import RunOrigin
from models.domain.tool import CreateCodeReferenceResponse, ToolErrorResponse
from tool.context import ToolContext
from tool.spec import ToolSpec

_DESCRIPTION = (
    "Scan the project's code for the todoMbarePilot{...} comments and gather them in one code reference note "
    "(rewritten at every scan). You get only how many comments and files, and the note's link: give the link to "
    "the user, who opens and edits the note. You never see the comments."
)


def build(context: ToolContext) -> Tool:

    @tool(name="create_code_reference", description=_DESCRIPTION)
    def create_code_reference() -> CreateCodeReferenceResponse | ToolErrorResponse:
        if context.code_todos is None or context.project_name is None or context.origin is not RunOrigin.CHAT:
            return ToolErrorResponse(error="Scansione dei commenti disponibile solo nel chatbot di un progetto.")
        project_name = context.require_project()
        try:
            scan = context.require_code_todos().save(project_name)
        except AppError as exc:
            return ToolErrorResponse(error=str(exc))
        return CreateCodeReferenceResponse(
            **scan.model_dump(exclude={"note"}), note=scan.note, link=note_link(project_name, scan.note) if scan.note else None,
        )

    return create_code_reference


def note_link(project_name: str, note: str) -> str:
    """The note in the app (Dati); the refiner's panel opens it in place."""
    return f"/projects/{quote(project_name)}/data?note={quote(note)}"


CREATE_CODE_REFERENCE = ToolSpec(
    name="create_code_reference",
    description="Raccoglie i commenti todoMbarePilot{…} del codice in un riferimento codice; all'agente arrivano solo i conteggi.",
    build=build,
    chatbot_only=True,
)
