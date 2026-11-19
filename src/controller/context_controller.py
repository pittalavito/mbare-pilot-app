"""A project's context (RAG), under /projects/{project}: the documents of
``context/`` (saving one indexes it), the state of the index, «Reindicizza
tutto» and a search to try it from the UI (what the agents get); the general
context of the definitions (how the app works, plan 26), read only."""
from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from controller.dependencies import project_data_service, rag_service, repository_map_service
from core.error import NotFoundError
from domain.rag.chunking import title_of
from models.controller.project_data import ContextSavedResponse, ContextSearchRequest, DataFileResponse, NoteRequest, NoteResponse
from models.domain.rag import RagHit, RagIndexState
from service.project_data_service import ProjectDataService
from service.rag_service import RagService
from service.repository_map_service import RepositoryMapService

router = APIRouter(prefix="/projects/{project}", tags=["context"])


class GeneralDocument(BaseModel):
    name: str
    title: str
    content: str


@router.get("/context")
def list_context(project: str, service: ProjectDataService = Depends(project_data_service)) -> list[DataFileResponse]:
    return [DataFileResponse.from_file(item) for item in service.list_context(project)]


@router.get("/context/{name}")
def read_context(project: str, name: str, service: ProjectDataService = Depends(project_data_service)) -> NoteResponse:
    return NoteResponse(name=name, content=service.read_context(project, name))


@router.put("/context/{name}")
def save_context(project: str, name: str, request: NoteRequest, service: ProjectDataService = Depends(project_data_service),
                 rag: RagService = Depends(rag_service)) -> ContextSavedResponse:
    """Create or overwrite, then index it (best effort: ``index_error`` says why it was not)."""
    saved = service.save_context(project, name, request.content)
    return ContextSavedResponse(name=saved.name, index_error=rag.index_quietly(project, saved.name))


@router.delete("/context/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_context(project: str, name: str, service: ProjectDataService = Depends(project_data_service),
                   rag: RagService = Depends(rag_service)) -> Response:
    if not service.delete_context(project, name):
        raise NotFoundError(f"Documento di contesto non trovato: {name}")
    rag.remove_context(project, name)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/context/repository-map")
def generate_repository_map(project: str, service: RepositoryMapService = Depends(repository_map_service)) -> ContextSavedResponse:
    """«🗺 Genera mappa dei repository» (plan 27): context/repository.md, only its generated part rewritten; indexed."""
    name, error = service.generate(project)
    return ContextSavedResponse(name=name, index_error=error)


@router.get("/context-general")
def general_context(project: str, rag: RagService = Depends(rag_service)) -> list[GeneralDocument]:
    """The general context (``definition/context/*.md``): edited in the definitions, read only here."""
    return [GeneralDocument(name=name, title=title_of(text, name.removesuffix(".md")), content=text) for name, text in rag.general_documents()]


@router.get("/context-index")
def context_index(project: str, rag: RagService = Depends(rag_service)) -> RagIndexState:
    """How many documents and pieces are indexed, and with which embedder."""
    return rag.state(project)


@router.post("/context-index/reindex")
def reindex(project: str, rag: RagService = Depends(rag_service)) -> RagIndexState:
    """Every context document and done activity with «Imparato» (unchanged ones are not embedded again)."""
    return rag.reindex(project)


@router.post("/context-index/search")
def search(project: str, request: ContextSearchRequest, rag: RagService = Depends(rag_service)) -> list[RagHit]:
    """What search_context gives the agents for this question (Copilot: only the project's pieces)."""
    return rag.search(project, request.question)
