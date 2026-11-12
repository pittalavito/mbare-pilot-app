"""search_context: the project's context index (RAG, service/rag_service.py):
the documents of ``context/`` and the done activities with «Imparato». The
best pieces for a question, each with where it comes from, to cite it.
Costs tokens only when called; replaces read_context, which read everything."""
from typing import Annotated

from datapizza.tools import Tool, tool

from core.error import AppError
from models.domain.tool import SearchContextResponse, ToolErrorResponse
from tool.context import ToolContext
from tool.spec import ToolSpec


def build(context: ToolContext) -> Tool:

    @tool(name="search_context", description=(
        "Search the project's context (architecture, conventions, decisions, runbooks, glossary, lessons of done activities) "
        "for a question: the best pieces with their document and section. Write a specific question, e.g. from what the user "
        "said in the conversation; cite the document and section you use."
    ))
    def search_context(question: Annotated[str, "What you want to know, in a sentence."]) -> SearchContextResponse | ToolErrorResponse:
        try:
            hits = context.require_rag().search(context.require_project(), question)
        except AppError as exc:
            return ToolErrorResponse(error=str(exc))
        if not hits:
            return ToolErrorResponse(error="Il contesto del progetto è vuoto o non indicizzato (Progetto → Contesto).")
        return SearchContextResponse(hits=hits)

    return search_context


SEARCH_CONTEXT = ToolSpec(
    name="search_context",
    description="Cerca nel contesto del progetto (documenti di contesto e attività fatte con «Imparato»), con le fonti.",
    build=build,
)
