"""A project's Atlassian site, under /projects/{project}/atlassian. The API
token is write-only: GET says whether one is saved, never returns it."""
from fastapi import APIRouter, Depends, Response, status

from controller.dependencies import atlassian_service
from core.error import NotFoundError
from models.controller.atlassian import AtlassianSettingsRequest, AtlassianSettingsResponse, AtlassianUserResponse
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
