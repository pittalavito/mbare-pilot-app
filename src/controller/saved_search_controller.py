"""Saved searches in the code (plan 34), under /projects/{project}/code-search:
the defaults of the definitions plus the project's own, written and removed
in the project; «✨ Regex» proposes a regex from a description in words."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from controller.dependencies import saved_search_service
from models.domain.code_search import RegexProposal, SavedSearch, SavedSearchView
from service.saved_search_service import SavedSearchService

router = APIRouter(prefix="/projects/{project}/code-search", tags=["saved-searches"])


class SavedSearchBody(SavedSearch):
    replacing: str = ""
    """The name it had, when renamed; ``""`` = none."""


class RegexRequest(BaseModel):
    description: str
    """What to look for, in words."""


@router.get("/saved")
def list_saved(project: str, service: SavedSearchService = Depends(saved_search_service)) -> list[SavedSearchView]:
    """The defaults (``origin: app``) and the project's own (``origin: progetto``, they replace a default with the same name)."""
    return service.searches(project)


@router.put("/saved")
def save_saved(project: str, request: SavedSearchBody, service: SavedSearchService = Depends(saved_search_service)) -> list[SavedSearchView]:
    """The search in the project, by name (400 for a broken regex); the list after."""
    return service.save(project, SavedSearch(**request.model_dump(exclude={"replacing"})), request.replacing)


@router.delete("/saved/{name}")
def delete_saved(project: str, name: str, service: SavedSearchService = Depends(saved_search_service)) -> list[SavedSearchView]:
    """The project's search removed (404 when it has none with that name); a default it replaced comes back."""
    return service.delete(project, name)


@router.post("/regex")
def propose_regex(project: str, request: RegexRequest, service: SavedSearchService = Depends(saved_search_service)) -> RegexProposal:
    """«✨ Regex»: one call to the agent ``regex`` (400 without a description, 502 when the model fails)."""
    return service.propose_regex(project, request.description)
