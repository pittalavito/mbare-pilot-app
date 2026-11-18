"""«▶️ Lavora attività» (plan 12a): the Pianificatore's plan of an activity
(the agent tasks to create, in order, with the pre/post development tasks
around each development, plan 22) and the path of each task, the steps the
app derives from the task and its Copilot session."""
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field

from models.domain.note import TaskType


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PlannedTask(BaseModel):
    """One task as the model proposes it (structured answer)."""
    title: str = Field(description="Titolo breve del task, all'imperativo.")
    type: TaskType = Field(description="pre_dev (prima di uno sviluppo), development (cambia il codice), post_dev (dopo uno sviluppo), "
                                       "analysis, confluence oppure jira.")
    repository: str = Field("", description="Il repository dove si lavora, uno dell'elenco; vuoto se non serve.")
    items: list[int] = Field(default_factory=list, description="I numeri delle voci da cui nasce; vuoto per un task nuovo.")
    reason: str = Field("", description="Perché questo task, in una riga.")
    objective: str = Field("", description="Obiettivo: cosa deve ottenere, in una o due frasi.")
    criteria: list[str] = Field(default_factory=list, description="Criteri di accettazione, brevi e verificabili.")
    steps: list[str] = Field(default_factory=list, description="Solo per pre_dev e post_dev: i passi da fare, uno per riga "
                                                               "(comandi git, maven o altri); vuoto per gli altri tipi.")


class PlanAnswer(BaseModel):
    """The Pianificatore's whole answer: the tasks in the order to do them."""
    tasks: list[PlannedTask] = Field(default_factory=list)


class PlanProposal(PlannedTask):
    """A proposed task in clear, as the user confirms, corrects or discards it."""
    id: int
    item_texts: list[str] = []
    """The texts of its items (to show them)."""
    new: bool = False
    """No item: a task for something the todo list does not have (it becomes an item too)."""


class PlanTask(BaseModel):
    """A task of the confirmed plan, in its place."""
    task: str
    """The agent task's note."""
    repository: str = ""
    """Where to delegate it (proposed by the Pianificatore)."""


class ActivityPlan(BaseModel):
    """The activity's one plan (plan 18): the tasks created, in order, the
    Pianificatore's proposals still waiting for the user, and how the round goes."""
    id: int | None = None
    project_name: str
    activity: str
    """The activity's note."""
    run_id: str = ""
    """The Pianificatore's latest call (agent run: tokens, cost); ``""`` = only tasks written by hand."""
    proposals: list[PlanProposal] = []
    """Waiting for the user (none = nothing to choose)."""
    tasks: list[PlanTask] = []
    """The tasks created, in order: the round follows them."""
    cost_eur: float = 0.0
    """Every call of the Pianificatore for this activity."""
    paused: bool = True
    """The round starts only with «▶️ Avvia» and stops with «⏸ Pausa»."""
    errors: dict[str, str] = {}
    """Why the round's delegation failed, as ``<task>|delegate`` → error."""
    auto_approve: bool = False
    """The round gives the ok to Copilot's plan by itself (developments only)."""
    approved: list[str] = []
    """The tasks whose plan the round approved by itself (once each)."""
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class PlanChoice(BaseModel):
    """A proposal the user keeps, as corrected, or a task written by hand (``id`` None,
    with the numbers of its ``items``); the order of the choices is the plan's."""
    id: int | None = None
    items: list[int] = []
    """Only for a task written by hand: the items it covers."""
    title: str = Field(min_length=1)
    type: TaskType
    repository: str = ""
    objective: str = ""
    criteria: list[str] = []
    steps: list[str] = []
    """The suggested steps of a pre/post development task."""


class StepState(StrEnum):
    TODO = "todo"
    YOU = "you"
    """Waiting for the user: a control point."""
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class StepKey(StrEnum):
    DELEGATE = "delegate"
    """The delegation to Copilot (its first planning turn)."""
    COPILOT_PLAN = "copilot_plan"
    """Copilot's plan: «Ok, parti» (developments)."""
    EXECUTION = "execution"
    ANSWER = "answer"
    """Copilot's answer, saved as a note (the types that do not change the code)."""
    FINAL = "final"
    """«Conferma finale» of the changes: the task becomes done."""
    OPERATION = "operation"
    """A pre/post development task (plan 22): Dev or the user does it, then «Fatto»."""


STEP_LABELS: dict[StepKey, str] = {
    StepKey.DELEGATE: "Delega a Copilot",
    StepKey.COPILOT_PLAN: "Piano di Copilot",
    StepKey.EXECUTION: "Esecuzione",
    StepKey.ANSWER: "Risposta di Copilot",
    StepKey.FINAL: "Conferma finale",
    StepKey.OPERATION: "Dev o a mano",
}


RETRYABLE: set[StepKey] = {StepKey.DELEGATE}
"""The failed steps the user can run again."""


def step_id(task: str, step: StepKey) -> str:
    return f"{task}|{step.value}"


class PathStep(BaseModel):
    key: StepKey
    label: str
    state: StepState
    detail: str = ""


class PathTask(BaseModel):
    task: str
    title: str
    type: TaskType
    status: str
    """The task's status (or ``missing`` when its note was deleted)."""
    repository: str = ""
    session_id: int | None = None
    """Its latest Copilot session."""
    steps: list[PathStep] = []
    current: bool = False
    """The first task not done: the one the path is at."""


class ActivityPath(BaseModel):
    """The plan of an activity and, once confirmed, where each task is."""
    plan: ActivityPlan | None = None
    tasks: list[PathTask] = []
    summary: str = ""
    """12c: once no task is left to do, what the path did (composed by the code), to put in «Imparato»."""


class PlanOptions(BaseModel):
    """How the round goes: the automatic ok to Copilot's plan."""
    auto_approve: bool = False
