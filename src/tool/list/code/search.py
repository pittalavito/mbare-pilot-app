"""search_code and save_code_search: the free search in the project's code
(service/code_search_service.py) for the agents. ``search_code`` (Refiner,
Dev) gives only a few short matched lines, never whole files: the agent's
masking hides them like everything else it reads. ``save_code_search`` (only
Dev, who works on the code and first moves to the right branch) writes the
search as a code reference linked to the agent task the user indicated, so
Copilot reads it. Only in a chatbot's run of a project."""
from pydantic import BaseModel, Field

from core.error import ValidationError
from domain.project.links import note_link
from models.domain.agent import RunOrigin
from models.domain.code_search import CodeQuery
from models.domain.tool import CodeLine, SaveCodeSearchResponse, SearchCodeResponse
from tool.context import ToolContext
from tool.spec import params_tool

MAX_LINES = 30
"""The lines an agent gets at most."""
LINE_CHARS = 200
"""How long a line it gets at most."""


class SearchParams(BaseModel):
    query: str = Field("", description="The text to look for (e.g. '@Deprecated', 'OrderService'); with regex=true a regular expression.")
    regex: bool = Field(False, description="True = query is a regular expression.")
    files: str = Field("", description="Optional glob of the files, e.g. '*.java' or 'src/main/**'.")
    repository: str = Field("", description="Optional: only this repository of the project.")


class SaveParams(SearchParams):
    task: str = Field("", description="The agent task the user indicated (its note name, e.g. agent-task-login.md): the reference is linked to it.")
    title: str = Field("", description="The reference's title; empty = the text searched. Saved again with the same title, it is rewritten.")


def _query(params: SearchParams) -> CodeQuery:
    if not params.query.strip():
        raise ValidationError("Scrivi cosa cercare (query).")
    return CodeQuery(query=params.query, regex=params.regex, files=params.files, repository=params.repository)


def _chat(context: ToolContext) -> str:
    if context.code_search is None or context.project_name is None or context.origin is not RunOrigin.CHAT:
        raise ValidationError("Ricerca nel codice disponibile solo nel chatbot di un progetto.")
    return context.require_project()


def _search(context: ToolContext, params: SearchParams) -> SearchCodeResponse:
    project = _chat(context)
    result = context.require_code_search().search(project, _query(params), limit=MAX_LINES, chars=LINE_CHARS)
    return SearchCodeResponse(matches=[CodeLine(**match.model_dump()) for match in result.matches],
                              total=result.total, files=result.files, truncated=result.truncated)


def _save(context: ToolContext, params: SaveParams) -> SaveCodeSearchResponse:
    project = _chat(context)
    if not params.task.strip():
        raise ValidationError("Indica il task a cui collegare il riferimento (task).")
    saved = context.require_code_search().save(project, _query(params), params.title, [params.task.strip()])
    return SaveCodeSearchResponse(note=saved.note, created=saved.created, total=saved.total, link=note_link(project, saved.note))


SEARCH_CODE = params_tool(
    "search_code",
    "Search the project's code (plain text, or a regex with regex=true; optional glob of files and repository). "
    f"You get at most {MAX_LINES} matched lines, cut at {LINE_CHARS} characters, never whole files; "
    "total and files say how many more: narrow the search to see them.",
    SearchParams, _search, chatbot_only=True,
)

SAVE_CODE_SEARCH = params_tool(
    "save_code_search",
    "Save a code search as a code reference (every match as file:line → line) linked to the agent task the user "
    "indicated, so Copilot reads it. Ask the user before saving; give them the link you get back.",
    SaveParams, _save, writes=True, chatbot_only=True,
)
