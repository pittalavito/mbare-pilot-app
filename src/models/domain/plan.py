"""«▶️ Lavora attività» (plan 12a): the Pianificatore's plan of an activity
(the agent tasks to create, in order; each development with its Pre and Post,
plan 34) and the path of each task, the steps the app derives from the task,
its Copilot session and the plan."""
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field

from models.domain.note import DevPhase, Phase, TaskType


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PlannedPhase(BaseModel):
    """A development's Pre or Post as the model proposes it."""
    steps: list[str] = Field(default_factory=list, description="I passi da fare a parole, uno per voce.")
    commands: list[str] = Field(default_factory=list, description="I comandi shell da lanciare nel repository, sicuri e ripetibili, "
                                                                  "uno per voce (es. mvn -B clean install); vuoto se non servono.")
    automation: str = Field(default="", description="Il nome di un'automation del progetto da lanciare dopo i comandi, una dell'elenco; "
                                                    "vuoto se non serve.")


class PlannedTask(BaseModel):
    """One task as the model proposes it (structured answer)."""
    title: str = Field(description="Titolo breve del task, all'imperativo.")
    type: TaskType = Field(description="development (cambia il codice), analysis, confluence oppure jira.")
    repository: str = Field("", description="Il repository dove si lavora, uno dell'elenco; vuoto se non serve.")
    items: list[int] = Field(default_factory=list, description="I numeri delle voci da cui nasce; vuoto per un task nuovo.")
    reason: str = Field("", description="Perché questo task, in una riga.")
    objective: str = Field("", description="Obiettivo: cosa deve ottenere, in una o due frasi.")
    criteria: list[str] = Field(default_factory=list, description="Criteri di accettazione, brevi e verificabili.")
    pre: PlannedPhase = Field(default_factory=PlannedPhase, description="Solo per development: cosa fare prima di delegare "
                                                                         "(branch, aggiornamento, build); vuoto per gli altri tipi.")
    post: PlannedPhase = Field(default_factory=PlannedPhase, description="Solo per development: cosa fare dopo lo sviluppo "
                                                                          "(pulizia, test, commit); vuoto per gli altri tipi.")


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


class OperationState(StrEnum):
    """«🤖 Automatico» of a development's Pre or Post (plan 25, plan 34)."""
    QUEUED = "queued"
    RUNNING = "running"
    FAILED = "failed"
    DONE = "done"


class OperationRun(BaseModel):
    """The commands, then the automation, of a development's Pre or Post, run by the worker without an agent."""
    state: OperationState = OperationState.QUEUED
    output: str = ""
    """Each command (``$ command``) with the last lines of its output, then the automation's."""
    error: str = ""
    """Why it stopped (the command that failed, the automation's error)."""
    pipeline_run_id: int | None = None
    """The automation's run, once queued."""


class PhaseState(StrEnum):
    """How a development's Pre or Post finished (plan 34)."""
    DONE = "done"
    SKIPPED = "skipped"


def phase_id(task: str, phase: Phase) -> str:
    """The key of a development's Pre or Post in the plan's ``operations`` and ``phases``."""
    return f"{task}|{phase.value}"


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
    operations: dict[str, OperationRun] = {}
    """«🤖 Automatico» of the developments' Pre and Post, by ``<task>|pre`` or ``<task>|post`` (plan 25, plan 34)."""
    phases: dict[str, PhaseState] = {}
    """The Pre and Post finished, by ``<task>|pre`` or ``<task>|post``: done or skipped (plan 34)."""
    auto_skip_empty: bool = False
    """The round skips by itself the Pre and Post without commands nor automation (plan 34)."""
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
    pre: DevPhase = DevPhase()
    """A development's Pre (plan 34)."""
    post: DevPhase = DevPhase()
    """A development's Post (plan 34)."""
    references: list[str] | None = None
    """The references to link (plan 33: the ones not needed taken off); None = all the activity's."""


class StepState(StrEnum):
    TODO = "todo"
    YOU = "you"
    """Waiting for the user: a control point."""
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class StepKey(StrEnum):
    PRE = "pre"
    """A development's Pre (plan 34): «🤖 Automatico» (commands and automation, or Dev) or by hand, then «Fatto»; or «Salta»."""
    DELEGATE = "delegate"
    """The delegation to Copilot (its first planning turn)."""
    COPILOT_PLAN = "copilot_plan"
    """Copilot's plan: «Ok, parti» (developments)."""
    EXECUTION = "execution"
    ANSWER = "answer"
    """Copilot's answer, saved as a note (the types that do not change the code)."""
    FINAL = "final"
    """«Conferma finale» of the changes: the task becomes done."""
    POST = "post"
    """A development's Post (plan 34), after the final confirmation: like Pre."""
    PUBLISH = "publish"
    """A Confluence or Jira task (plan 33): the draft saved, «📤 Pubblica» (the draft editable); then it is done."""


STEP_LABELS: dict[StepKey, str] = {
    StepKey.PRE: "Pre",
    StepKey.DELEGATE: "Delega a Copilot",
    StepKey.COPILOT_PLAN: "Piano di Copilot",
    StepKey.EXECUTION: "Esecuzione",
    StepKey.ANSWER: "Risposta di Copilot",
    StepKey.FINAL: "Conferma finale",
    StepKey.POST: "Post",
    StepKey.PUBLISH: "Pubblica",
}


PHASE_STEPS: dict[Phase, StepKey] = {Phase.PRE: StepKey.PRE, Phase.POST: StepKey.POST}

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
    """How the round goes: the automatic ok to Copilot's plan, the empty Pre and Post skipped by themselves.
    Only the options sent change."""
    auto_approve: bool = False
    auto_skip_empty: bool = False
