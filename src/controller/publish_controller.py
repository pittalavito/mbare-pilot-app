"""«Pubblica su Confluence/Jira» of a task's draft (blocco 10), under
/projects/{project}/agent-tasks/{note}/publish: the preview (target, text,
comparison, unmasked aliases), then the publication on the user's click."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from controller.dependencies import publish_service
from models.domain.publish import PublishPreview, PublishResult
from service.publish_service import PublishService

router = APIRouter(prefix="/projects/{project}/agent-tasks/{note}", tags=["publish"])


class PublishRequest(BaseModel):
    """For a new page or issue (ignored when the task links one to update); empty = the project's default."""
    space_key: str = ""
    parent_id: str = ""
    project_key: str = ""
    issue_type: str = ""


@router.get("/publish")
def preview(project: str, note: str, service: PublishService = Depends(publish_service)) -> PublishPreview:
    """What «Pubblica» would do; changes nothing."""
    return service.preview(project, note)


@router.post("/publish")
def publish(project: str, note: str, request: PublishRequest, service: PublishService = Depends(publish_service)) -> PublishResult:
    """Create or update the page / issue; the task goes «done» and the page / issue is a reference linked to it."""
    return service.publish(project, note, **request.model_dump())
