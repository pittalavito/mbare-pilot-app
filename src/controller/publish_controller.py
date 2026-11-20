"""«Pubblica su Confluence/Jira» of a task's draft, under
/projects/{project}/agent-tasks/{note}/publish: the preview (target, text,
comparison, unmasked aliases), then the publication on the user's click."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from controller.dependencies import plan_service, publish_service
from models.domain.publish import PublishPreview, PublishResult
from service.plan_service import PlanService
from service.publish_service import PublishService

router = APIRouter(prefix="/projects/{project}/agent-tasks/{note}", tags=["publish"])


class PublishRequest(BaseModel):
    """For a new page or issue (ignored when the task links one to update); empty = the project's default."""
    space_key: str = ""
    parent_id: str = ""
    project_key: str = ""
    issue_type: str = ""
    title: str = ""
    body: str = ""
    """The draft as edited in the window; empty = the draft as saved."""


@router.get("/publish")
def preview(project: str, note: str, service: PublishService = Depends(publish_service)) -> PublishPreview:
    """What «Pubblica» would do; changes nothing."""
    return service.preview(project, note)


@router.post("/publish")
def publish(project: str, note: str, request: PublishRequest, service: PublishService = Depends(publish_service),
            plans: PlanService = Depends(plan_service)) -> PublishResult:
    """Create or update the page / issue; the task goes «done», the page / issue is a reference linked to it and to the
    next task of its activity in place of the draft, which is deleted."""
    result = service.publish(project, note, **request.model_dump())
    plans.pass_on(project, note, result.reference, replacing=result.draft)
    return result
