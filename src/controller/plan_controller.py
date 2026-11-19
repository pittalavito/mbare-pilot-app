"""An activity's steps «Pianifica», «Lavora» and «Chiudi» (plan 18), under
/projects/{project}: the Pianificatore's proposals (one call), creating the
tasks (no LLM), the round of the tasks and its settings, and the closing
(what was learned goes in context/imparato.md)."""
from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from controller.dependencies import activity_close_service, operation_service, plan_service
from models.domain.activity_close import ActivityArchived, ActivityClosed, LearnedDraft
from models.domain.plan import ActivityPath, ActivityPlan, PlanChoice, PlanOptions, StepKey
from service.activity_close_service import ActivityCloseService
from service.operation_service import OperationService
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


class TaskRequest(BaseModel):
    task: str


class AutoResponse(BaseModel):
    plan: ActivityPlan
    pending_commands: list[str] = []
    """Commands not allowed: nothing started, each is a request to answer (then «Automatico» again)."""


class ArchiveRequest(BaseModel):
    delete_references: list[str] = []
    """The references to delete with it (plan 33); the others stay."""


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
    """The automatic ok to Copilot's plan."""
    return service.set_options(project, activity, request)


@router.post("/activities/{activity}/plan/retry")
def retry_step(project: str, activity: str, request: StepRequest, service: PlanService = Depends(plan_service)) -> ActivityPlan:
    """Run a failed delegation again (at the round's next turn)."""
    return service.retry(project, activity, request.task, request.step)


@router.post("/activities/{activity}/plan/done")
def mark_done(project: str, activity: str, request: TaskRequest, service: PlanService = Depends(plan_service)) -> ActivityPlan:
    """«✅ Fatto» on a pre/post development task (plan 22): done by Dev or by hand, the round goes on."""
    return service.mark_done(project, activity, request.task)


@router.post("/activities/{activity}/plan/auto")
def start_auto(project: str, activity: str, request: TaskRequest, service: OperationService = Depends(operation_service)) -> AutoResponse:
    """«🤖 Automatico» on a pre/post development task (plan 25): its commands, then its automation, run by the worker;
    commands not allowed come back first, nothing started."""
    plan, pending = service.start(project, activity, request.task)
    return AutoResponse(plan=plan, pending_commands=pending)


@router.post("/activities/{activity}/learned")
def propose_learned(project: str, activity: str, service: ActivityCloseService = Depends(activity_close_service)) -> LearnedDraft:
    """One call to the agent ``imparato``: the points to remember (502 when the model fails)."""
    return service.propose_learned(project, activity)


@router.post("/activities/{activity}/close")
def close_activity(project: str, activity: str, request: CloseRequest,
                   service: ActivityCloseService = Depends(activity_close_service)) -> ActivityClosed:
    """What was learned at the top of context/imparato.md, the activity done, its round stopped."""
    return service.close(project, activity, request.learned)


@router.post("/activities/{activity}/archive")
def archive_activity(project: str, activity: str, request: ArchiveRequest,
                     service: ActivityCloseService = Depends(activity_close_service)) -> ActivityArchived:
    """«🗄 Archivia» (plan 33): a summary note archivio-<attività>.md; the activity, its tasks, answers, drafts, plan and
    Copilot sessions deleted, and the references chosen (409 when it is not closed or a Copilot session is running)."""
    return service.archive(project, activity, request.delete_references)


@router.post("/activities/{activity}/reopen", status_code=status.HTTP_204_NO_CONTENT)
def reopen_activity(project: str, activity: str, service: ActivityCloseService = Depends(activity_close_service)) -> Response:
    """Back to «in progress»; context/imparato.md is not touched."""
    service.reopen(project, activity)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
