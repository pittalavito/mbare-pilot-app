"""«▶️ Lavora attività» (plan 12a), under /projects/{project}: the Pianificatore's
proposals for an activity (one call), confirming them (the tasks are created,
no LLM) or dismissing them, the activity's path and «Conferma del task»."""
from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from controller.dependencies import plan_service
from models.domain.plan import ActivityPath, ActivityPlan, PlanChoice, StepKey
from service.plan_service import PlanService

router = APIRouter(prefix="/projects/{project}", tags=["plan"])


class PlanConfirmRequest(BaseModel):
    choices: list[PlanChoice]
    """The proposals kept, as corrected, in the plan's order."""


@router.get("/activities/{activity}/path")
def activity_path(project: str, activity: str, service: PlanService = Depends(plan_service)) -> ActivityPath:
    """The plan waiting for a choice, or the confirmed plan with the steps of each task."""
    return service.path(project, activity)


@router.post("/activities/{activity}/plan")
def propose_plan(project: str, activity: str, service: PlanService = Depends(plan_service)) -> ActivityPlan:
    """One call to the Pianificatore (the secretary's model): the proposed tasks (502 when the model fails)."""
    return service.propose(project, activity)


@router.post("/activities/{activity}/plan/confirm")
def confirm_plan(project: str, activity: str, request: PlanConfirmRequest, service: PlanService = Depends(plan_service)) -> ActivityPlan:
    """The chosen proposals become agent tasks «in refinement», linked to their items (409 when the plan no longer waits)."""
    return service.confirm(project, activity, request.choices)


@router.post("/activities/{activity}/plan/dismiss")
def dismiss_plan(project: str, activity: str, service: PlanService = Depends(plan_service)) -> ActivityPlan:
    return service.dismiss(project, activity)


@router.post("/agent-tasks/{task}/confirm", status_code=status.HTTP_204_NO_CONTENT)
def confirm_task(project: str, task: str, service: PlanService = Depends(plan_service)) -> Response:
    """«Conferma del task»: from «in refinement» to «to do» (409 when already confirmed, 400 without an objective)."""
    service.confirm_task(project, task)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class PauseRequest(BaseModel):
    paused: bool


class PrepareRequest(BaseModel):
    prepare: str = ""
    """``""`` (automatic), ``none``, ``dev`` or ``learned:<id>``."""


class StepRequest(BaseModel):
    task: str
    step: StepKey


@router.post("/activities/{activity}/plan/pause")
def pause_plan(project: str, activity: str, request: PauseRequest, service: PlanService = Depends(plan_service)) -> ActivityPlan:
    """Pause or resume the path (409 without a confirmed plan)."""
    return service.set_paused(project, activity, request.paused)


@router.post("/activities/{activity}/plan/prepare")
def prepare_plan(project: str, activity: str, request: PrepareRequest, service: PlanService = Depends(plan_service)) -> ActivityPlan:
    """How the path prepares the repositories before Copilot."""
    return service.set_prepare(project, activity, request.prepare)


@router.post("/activities/{activity}/plan/skip")
def skip_step(project: str, activity: str, request: StepRequest, service: PlanService = Depends(plan_service)) -> ActivityPlan:
    """Skip a task's preparation or verification."""
    return service.skip(project, activity, request.task, request.step)


@router.post("/activities/{activity}/plan/retry")
def retry_step(project: str, activity: str, request: StepRequest, service: PlanService = Depends(plan_service)) -> ActivityPlan:
    """Run a failed preparation, delegation (at the path's next turn) or verification (now) again."""
    return service.retry(project, activity, request.task, request.step)
