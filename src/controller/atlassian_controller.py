"""A project's Atlassian site, under /projects/{project}/atlassian: its
settings (the API token is write-only: GET says whether one is saved, never
returns it) and read-only access to its Jira issues and Confluence pages."""
from fastapi import APIRouter, Depends, Response, status

from controller.dependencies import atlassian_service
from core.error import NotFoundError
from models.controller.atlassian import (
    AtlassianSettingsRequest, AtlassianSettingsResponse, AtlassianUserResponse, ConfluencePageResponse,
    ConfluenceSearchHitResponse, JiraIssueResponse,
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


@router.get("/confluence/search")
def search_pages(project: str, q: str, space: str | None = None, limit: int = 25,
                 service: AtlassianService = Depends(atlassian_service)) -> list[ConfluenceSearchHitResponse]:
    """Full-text search, in ``space`` or in every space."""
    hits = service.site(project).search_pages(q, space, limit)
    return [ConfluenceSearchHitResponse.from_hit(hit) for hit in hits]
