"""search_context: the project's context index (RAG, service/rag_service.py):
the documents of the project's ``context/`` and the general context of the
definitions (how the app works, plan 26). The best pieces for a question,
each with where it comes from (``origin``: progetto / generale), to cite it;
the project's context wins over the general one.
Costs tokens only when called; replaces read_context, which read everything."""
from typing import Annotated

from datapizza.tools import Tool, tool

from core.error import AppError
from models.domain.tool import SearchContextResponse, ToolErrorResponse
from tool.context import ToolContext
from tool.spec import ToolSpec


def build(context: ToolContext) -> Tool:

    @tool(name="search_context", description=(
        "Search the context for a question: the project's (architecture, conventions, decisions, runbooks, glossary, lessons "
        "of done activities; origin 'progetto') and how this app works (task types and states, activities and their round, "
        "Copilot, the developments' pre and post, references, automations, tools; origin 'generale'). The best pieces with their "
        "document and section. Write a specific question; the project's context wins over the general one; cite what you use."
    ))
    def search_context(question: Annotated[str, "What you want to know, in a sentence."]) -> SearchContextResponse | ToolErrorResponse:
        try:
            hits = context.require_rag().search(context.require_project(), question)
        except AppError as exc:
            return ToolErrorResponse(error=str(exc))
        if not hits:
            return ToolErrorResponse(error="Il contesto è vuoto o non indicizzato (Progetto → Contesto).")
        return SearchContextResponse(hits=hits)

    return search_context


SEARCH_CONTEXT = ToolSpec(
    name="search_context",
    description="Cerca nel contesto del progetto e in quello generale (come funziona l'app), con le fonti; vince il progetto.",
    build=build,
)
