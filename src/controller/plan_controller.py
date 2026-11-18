"""An activity's steps «Pianifica», «Lavora» and «Chiudi» (plan 18), under
/projects/{project}: the Pianificatore's proposals (one call), creating the
tasks (no LLM), the round of the tasks and its settings, and the closing
(what was learned goes in context/imparato.md)."""
from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from controller.dependencies import activity_close_service, plan_service
from models.domain.activity_close import ActivityClosed, LearnedDraft
from models.domain.plan import ActivityPath, ActivityPlan, PlanChoice, PlanOptions, StepKey, TaskFields
from service.activity_close_service import ActivityCloseService
from service.plan_service import PlanService

router = APIRouter(prefix="/projects/{project}", tags=["plan"])


class PlanConfirmRequest(BaseModel):
    choices: list[PlanChoice]
    """The proposals kept, as corrected, and the tasks written by hand, in order."""


class PauseRequest(BaseModel):
    paused: bool


class StepRequest(BaseModel):
    task: str
    step: StepKey


class TaskFieldsRequest(BaseModel):
    task: str
    step: StepKey
    fields: dict[str, str] = {}
    """Empty = back to the activity's template."""


class CloseRequest(BaseModel):
    learned: str = ""
    """What to remember, one point per line; empty = context/imparato.md is not touched."""


@router.get("/activities/{activity}/path")
def activity_path(project: str, activity: str, service: PlanService = Depends(plan_service)) -> ActivityPath:
    """The activity's plan (proposals waiting, tasks) with the steps of each task; the summary once none is left."""
    return service.path(project, activity)


@router.post("/activities/{activity}/plan")
def propose_plan(project: str, activity: str, service: PlanService = Depends(plan_service)) -> ActivityPlan:
    """One call to the agent ``pianificatore``: tasks for the items still uncovered (502 when the model fails)."""
    return service.propose(project, activity)


@router.post("/activities/{activity}/plan/confirm")
def confirm_plan(project: str, activity: str, request: PlanConfirmRequest, service: PlanService = Depends(plan_service)) -> ActivityPlan:
    """The chosen proposals and the tasks written by hand become agent tasks «to do» (409 when a proposal is gone)."""
    return service.confirm(project, activity, request.choices)


@router.post("/activities/{activity}/plan/dismiss")
def dismiss_plan(project: str, activity: str, service: PlanService = Depends(plan_service)) -> ActivityPlan:
    """The proposals waiting are dropped; the tasks stay."""
    return service.dismiss(project, activity)


@router.post("/activities/{activity}/plan/pause")
def pause_plan(project: str, activity: str, request: PauseRequest, service: PlanService = Depends(plan_service)) -> ActivityPlan:
    """«▶️ Avvia» (false) or «⏸ Pausa» (true); 409 without tasks."""
    return service.set_paused(project, activity, request.paused)


@router.post("/activities/{activity}/plan/options")
def plan_options(project: str, activity: str, request: PlanOptions, service: PlanService = Depends(plan_service)) -> ActivityPlan:
    """Before delegating (``none``, ``dev``, ``automation:<id>``) and the automation after the verification, each with its
    fields as a template (``{task}``, ``{note}``, ``{repository}``, ``{base}``), and the automatic ok."""
    return service.set_options(project, activity, request)


@router.post("/activities/{activity}/plan/skip")
def skip_step(project: str, activity: str, request: StepRequest, service: PlanService = Depends(plan_service)) -> ActivityPlan:
    """Skip a task's preparation, verification or automation after it."""
    return service.skip(project, activity, request.task, request.step)


@router.post("/activities/{activity}/plan/retry")
def retry_step(project: str, activity: str, request: StepRequest, service: PlanService = Depends(plan_service)) -> ActivityPlan:
    """Run a failed step again: preparation, delegation, automation (at the round's next turn) or the tests (now)."""
    return service.retry(project, activity, request.task, request.step)


@router.get("/activities/{activity}/plan/fields")
def task_fields(project: str, activity: str, task: str, step: StepKey, service: PlanService = Depends(plan_service)) -> TaskFields:
    """«⚙️ Campi»: what runs at ``step`` (prepare, after) for the task and its fields, resolved for it."""
    return service.task_fields(project, activity, task, step)


@router.put("/activities/{activity}/plan/fields")
def save_task_fields(project: str, activity: str, request: TaskFieldsRequest, service: PlanService = Depends(plan_service)) -> ActivityPlan:
    """The task's own fields for ``step`` (empty = the activity's template again)."""
    return service.set_task_fields(project, activity, request.task, request.step, request.fields)


@router.post("/activities/{activity}/learned")
def propose_learned(project: str, activity: str, service: ActivityCloseService = Depends(activity_close_service)) -> LearnedDraft:
    """One call to the agent ``imparato``: the points to remember (502 when the model fails)."""
    return service.propose_learned(project, activity)


@router.post("/activities/{activity}/close")
def close_activity(project: str, activity: str, request: CloseRequest,
                   service: ActivityCloseService = Depends(activity_close_service)) -> ActivityClosed:
    """What was learned at the top of context/imparato.md, the activity done, its round stopped."""
    return service.close(project, activity, request.learned)


@router.post("/activities/{activity}/reopen", status_code=status.HTTP_204_NO_CONTENT)
def reopen_activity(project: str, activity: str, service: ActivityCloseService = Depends(activity_close_service)) -> Response:
    """Back to «in progress»; context/imparato.md is not touched."""
    service.reopen(project, activity)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
