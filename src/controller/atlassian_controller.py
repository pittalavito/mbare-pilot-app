"""A project's Atlassian site, under /projects/{project}/atlassian: its
settings (the API token is write-only: GET says whether one is saved, never
returns it), read-only access to its Jira issues and Confluence pages, the
project's favorite issues and pages, and the copy of an issue or a page into the
project as a context reference (.../reference)."""
from fastapi import APIRouter, Depends, Response, status

from controller.dependencies import atlassian_service
from core.error import NotFoundError
from models.controller.atlassian import (
    AtlassianSettingsRequest,
    AtlassianSettingsResponse,
    AtlassianUserResponse,
    ConfluencePageResponse,
    ConfluenceSearchHitResponse,
    FavoriteRequest,
    FavoriteResponse,
    JiraIssueResponse,
    ReferenceImportRequest,
    ReferenceImportResponse,
)
from service.atlassian_service import AtlassianService

router = APIRouter(prefix="/projects/{project}/atlassian", tags=["atlassian"])


@router.get("")
def get_settings(project: str,
                 service: AtlassianService = Depends(atlassian_service)) -> AtlassianSettingsResponse | None:
    """None = not configured."""
    settings = service.get_settings(project)
    return AtlassianSettingsResponse.from_settings(settings) if settings else None


@router.put("")
def save_settings(project: str, request: AtlassianSettingsRequest,
                  service: AtlassianService = Depends(atlassian_service)) -> AtlassianSettingsResponse:
    """An empty ``api_token`` keeps the saved one."""
    return AtlassianSettingsResponse.from_settings(service.save_settings(project, **request.model_dump()))


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def remove_settings(project: str, service: AtlassianService = Depends(atlassian_service)) -> Response:
    if not service.remove_settings(project):
        raise NotFoundError(f"Atlassian non configurato per il progetto {project}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/check")
def check_connection(project: str, service: AtlassianService = Depends(atlassian_service)) -> AtlassianUserResponse:
    """The account the token belongs to; 502 when Atlassian refuses it."""
    return AtlassianUserResponse.from_user(service.site(project).check_connection())


# --------------------------------------------------------------------- Jira

@router.get("/jira/issues/{issue_key}")
def get_issue(project: str, issue_key: str,
              service: AtlassianService = Depends(atlassian_service)) -> JiraIssueResponse:
    """One issue by key (``PROJ-123``), with its description as plain text."""
    return JiraIssueResponse.from_issue(service.site(project).get_issue(issue_key))


@router.post("/jira/issues/{issue_key}/reference")
def issue_reference(project: str, issue_key: str, request: ReferenceImportRequest,
                    response: Response, service: AtlassianService = Depends(atlassian_service)) -> ReferenceImportResponse:
    """Copy the issue into the project as a context reference (201), or refresh
    the copy made before (200); linked from ``link_to`` (agent tasks, todo lists)."""
    name, created = service.reference_from_issue(project, issue_key, request.link_to)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return ReferenceImportResponse(name=name, created=created)


# --------------------------------------------------------------- Confluence

@router.get("/confluence/pages")
def list_pages(project: str, space: str | None = None, limit: int = 100,
               service: AtlassianService = Depends(atlassian_service)) -> list[ConfluencePageResponse]:
    """Pages of ``space`` (default: the project's space), without their body."""
    return [ConfluencePageResponse.from_page(page) for page in service.site(project).list_space_pages(space, limit)]


@router.get("/confluence/pages/{page_id}")
def get_page(project: str, page_id: str,
             service: AtlassianService = Depends(atlassian_service)) -> ConfluencePageResponse:
    """One page with its body as plain text."""
    return ConfluencePageResponse.from_page(service.site(project).get_page(page_id))


@router.post("/confluence/pages/{page_id}/reference")
def page_reference(project: str, page_id: str, request: ReferenceImportRequest,
                   response: Response, service: AtlassianService = Depends(atlassian_service)) -> ReferenceImportResponse:
    """Copy the page into the project as a context reference, as for an issue."""
    name, created = service.reference_from_page(project, page_id, request.link_to)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return ReferenceImportResponse(name=name, created=created)


@router.get("/confluence/search")
def search_pages(project: str, q: str, space: str | None = None, limit: int = 25,
                 service: AtlassianService = Depends(atlassian_service)) -> list[ConfluenceSearchHitResponse]:
    """Full-text search, in ``space`` or in every space."""
    hits = service.site(project).search_pages(q, space, limit)
    return [ConfluenceSearchHitResponse.from_hit(hit) for hit in hits]


# ---------------------------------------------------------------- favorites

@router.get("/favorites")
def list_favorites(project: str, service: AtlassianService = Depends(atlassian_service)) -> list[FavoriteResponse]:
    """Saved in the app: listing them never calls Atlassian."""
    return [FavoriteResponse.from_favorite(favorite) for favorite in service.list_favorites(project)]


@router.post("/favorites", status_code=status.HTTP_201_CREATED)
def add_favorite(project: str, request: FavoriteRequest,
                 service: AtlassianService = Depends(atlassian_service)) -> FavoriteResponse:
    """Already a favorite: the saved one comes back."""
    favorite = service.add_favorite(project, request.kind, request.ref, request.title, request.url)
    return FavoriteResponse.from_favorite(favorite)


@router.delete("/favorites/{favorite_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_favorite(project: str, favorite_id: int, service: AtlassianService = Depends(atlassian_service)) -> Response:
    service.remove_favorite(project, favorite_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
