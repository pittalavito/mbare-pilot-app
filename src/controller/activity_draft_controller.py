"""«📎 Da riferimenti» (plan 16), under /projects/{project}: the activity the
secretary proposes from the titles of the chosen references and context pieces
(one call, nothing created: the activity is created with POST /activities)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from controller.dependencies import activity_draft_service
from models.domain.activity_draft import ActivityDraft
from service.activity_draft_service import ActivityDraftService

router = APIRouter(prefix="/projects/{project}", tags=["activity-draft"])


class ActivityDraftRequest(BaseModel):
    references: list[str] = []
    """Reference notes of the project, by name."""
    context: list[str] = []
    """Titles of the chosen pieces of the context index (only text for the proposal)."""


@router.post("/activities/draft")
def draft_activity(project: str, request: ActivityDraftRequest,
                   service: ActivityDraftService = Depends(activity_draft_service)) -> ActivityDraft:
    """One call to the secretary's model: title, description and todo items (400 with nothing chosen, 502 when the model fails)."""
    return service.propose(project, request.references, request.context)
