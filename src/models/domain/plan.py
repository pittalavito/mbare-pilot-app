"""«▶️ Lavora attività» (plan 12a): the Pianificatore's plan of an activity
(the agent tasks to create, in order) and the path of each task, the steps
the app derives from the task and its Copilot session."""
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field

from models.domain.note import TaskType


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PlannedTask(BaseModel):
    """One task as the model proposes it (structured answer)."""
    title: str = Field(description="Titolo breve del task, all'imperativo.")
    type: TaskType = Field(description="development (cambia il codice), analysis, confluence oppure jira.")
    repository: str = Field("", description="Il repository dove si lavora, uno dell'elenco; vuoto se non serve.")
    items: list[int] = Field(default_factory=list, description="I numeri delle voci da cui nasce; vuoto per un task nuovo.")
    reason: str = Field("", description="Perché questo task, in una riga.")
    objective: str = Field("", description="Obiettivo: cosa deve ottenere, in una o due frasi.")
    criteria: list[str] = Field(default_factory=list, description="Criteri di accettazione, brevi e verificabili.")


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


class PlanStatus(StrEnum):
    PROPOSED = "proposed"
    """The proposals wait for the user."""
    CONFIRMED = "confirmed"
    """The tasks exist: the path follows them."""
    DISMISSED = "dismissed"


class PlanTask(BaseModel):
    """A task of the confirmed plan, in its place."""
    task: str
    """The agent task's note."""
    repository: str = ""
    """Where to delegate it (proposed by the Pianificatore)."""


class ActivityPlan(BaseModel):
    id: int | None = None
    project_name: str
    activity: str
    """The activity's note."""
    run_id: str
    """The Pianificatore's call (agent run: tokens, cost)."""
    status: PlanStatus = PlanStatus.PROPOSED
    proposals: list[PlanProposal] = []
    tasks: list[PlanTask] = []
    """Once confirmed: the tasks created, in order."""
    cost_eur: float = 0.0
    paused: bool = False
    """The automatic path (12b) stops where it is until resumed."""
    prepare: str = ""
    """How the path prepares the repositories before Copilot: ``none``, ``dev``
    («Prepara sviluppo»), ``learned:<id>`` (an automation learned from the
    Operator); ``""`` = the learned one if any, else «Prepara sviluppo» if any, else none."""
    skipped: list[str] = []
    """The steps skipped by the user, as ``<task>|<step>``."""
    errors: dict[str, str] = {}
    """Why a step the path ran failed (preparation, delegation), as ``<task>|<step>`` → error."""
    retries: dict[str, int] = {}
    """How many times the path sent a task's failed tests back to Copilot by itself."""
    before_automation: int | None = None
    """12c: an automation the path runs before each development task (after its confirmation)."""
    after_automation: int | None = None
    """12c: an automation the path runs after each development task's verification, before the final confirmation."""
    automation_runs: dict[str, int] = {}
    """The runs of those automations, as ``<task>|before`` / ``<task>|after`` → pipeline run id."""
    auto_approve: bool = False
    """12c: the path gives the ok to Copilot's plan by itself (developments only)."""
    approved: list[str] = []
    """The tasks whose plan the path approved by itself (once each)."""
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class PlanChoice(BaseModel):
    """A proposal the user keeps, as corrected; the order of the choices is the plan's."""
    id: int
    title: str = Field(min_length=1)
    type: TaskType
    repository: str = ""
    objective: str = ""
    criteria: list[str] = []


class StepState(StrEnum):
    TODO = "todo"
    YOU = "you"
    """Waiting for the user: a control point."""
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class StepKey(StrEnum):
    CONFIRM = "confirm"
    """«Conferma del task»: objective and criteria written by the Pianificatore."""
    BEFORE = "before"
    """12c: the activity's automation before each development task."""
    PREPARE = "prepare"
    """The repositories got ready before Copilot (developments): skippable."""
    DELEGATE = "delegate"
    """The delegation to Copilot (its first planning turn)."""
    COPILOT_PLAN = "copilot_plan"
    """Copilot's plan: «Ok, parti» (developments)."""
    EXECUTION = "execution"
    VERIFY = "verify"
    """«Verifica sviluppo»: cleaning and tests."""
    AFTER = "after"
    """12c: the activity's automation after each development task's verification."""
    ANSWER = "answer"
    """Copilot's answer, saved as a note (the types that do not change the code)."""
    FINAL = "final"
    """«Conferma finale» of the changes: the task becomes done."""


STEP_LABELS: dict[StepKey, str] = {
    StepKey.CONFIRM: "Conferma del task",
    StepKey.BEFORE: "Automation prima",
    StepKey.PREPARE: "Preparazione",
    StepKey.DELEGATE: "Delega a Copilot",
    StepKey.COPILOT_PLAN: "Piano di Copilot",
    StepKey.EXECUTION: "Esecuzione",
    StepKey.VERIFY: "Verifica",
    StepKey.AFTER: "Automation dopo",
    StepKey.ANSWER: "Risposta di Copilot",
    StepKey.FINAL: "Conferma finale",
}


SKIPPABLE: set[StepKey] = {StepKey.PREPARE, StepKey.VERIFY, StepKey.BEFORE, StepKey.AFTER}
"""The steps the user can skip."""
RETRYABLE: set[StepKey] = {StepKey.PREPARE, StepKey.DELEGATE, StepKey.VERIFY, StepKey.BEFORE, StepKey.AFTER}
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
    """12c: the activity's automations before and after each task, and the automatic ok to Copilot's plan."""
    before_automation: int | None = None
    after_automation: int | None = None
    auto_approve: bool = False
