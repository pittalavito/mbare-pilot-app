"""The projects' context index (RAG, service/rag_service.py): the documents
of ``context/`` and the done activities with «Imparato», split into pieces by
heading, embedded (masked first when the embedder is not local) and searched
by the Refiner and by Copilot (tool search_context)."""
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RagSource(StrEnum):
    CONTEXT = "context"
    """A ``.md`` of the project's ``context/`` folder."""
    GENERAL = "general"
    """A ``.md`` of the definitions' ``context/`` folder: how the app works, the same for every project (plan 26)."""


class RagPiece(BaseModel):
    """One piece of an indexed document, as stored."""
    position: int
    section: str = ""
    text: str
    embedding_model: str
    embedding: list[float]


class RagDocument(BaseModel):
    id: int | None = None
    project_name: str
    path: str
    """``context/<name>.md`` or ``notes/<activity>.md``: unique in the project."""
    source: RagSource
    title: str = ""
    content_hash: str
    indexed_at: datetime = Field(default_factory=_utc_now)


class RagHit(BaseModel):
    """A search result: the piece and where it comes from (to cite it)."""
    path: str = Field(description="Where it comes from: context/<name>.md (the project) or general/<name>.md (how the app works).")
    title: str = Field(description="The document's title.")
    section: str = Field(description="The section of the document ('' = its beginning).")
    text: str
    score: float = Field(description="0..1+: cosine similarity plus a bonus for the question's words found in the piece.")
    origin: str = Field("progetto", description="'progetto' (the project's context, it wins) or 'generale' (how the app works).")


class RagIndexState(BaseModel):
    """What the index of a project holds, for the Contesto tab."""
    documents: int
    pieces: int
    embedder: str
    """The embedder the project's index uses (``""`` = none can be built: why in ``error``)."""
    error: str | None = None
    general: int = 0
    """Of ``documents``, the general ones (the definitions' context, plan 26)."""
