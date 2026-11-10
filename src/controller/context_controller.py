"""A project's context (RAG), under /projects/{project}: the documents of
``context/`` (saving one indexes it), the state of the index, «Reindicizza
tutto» and a search to try it from the UI (what the Refiner and Copilot get)."""
from fastapi import APIRouter, Depends, Response, status

from controller.dependencies import project_data_service, rag_service
from core.error import NotFoundError
from models.controller.project_data import ContextSavedResponse, ContextSearchRequest, DataFileResponse, NoteRequest, NoteResponse
from models.domain.rag import RagHit, RagIndexState
from service.project_data_service import ProjectDataService
from service.rag_service import RagService

router = APIRouter(prefix="/projects/{project}", tags=["context"])


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
    return ContextSavedResponse(name=saved.name, index_error=rag.index_quietly(project, "context", saved.name))


@router.delete("/context/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_context(project: str, name: str, service: ProjectDataService = Depends(project_data_service),
                   rag: RagService = Depends(rag_service)) -> Response:
    if not service.delete_context(project, name):
        raise NotFoundError(f"Documento di contesto non trovato: {name}")
    rag.remove_context(project, name)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    """What search_context gives the Refiner and Copilot for this question."""
    return rag.search(project, request.question)
