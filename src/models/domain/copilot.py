"""Agent tasks delegated to GitHub Copilot CLI. A session is a conversation
with Copilot about one task on one repository of the project: first the
planning chat (Copilot reads the code and asks questions, it cannot change
anything; each turn runs in the worker), then, after the user's ok, the execution in the worker (Copilot
changes files, never commits). Copilot keeps the conversation itself
(``copilot_session_id``); the app keeps the messages to show them."""
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CopilotSessionStatus(StrEnum):
    PLANNING = "planning"
    """The chat before the ok: each message is a turn in plan mode (read only),
    run by the worker (``planning_turn``)."""
    QUEUED = "queued"
    """Ok given: waiting for the worker (one execution at a time per repository)."""
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def finished(self) -> bool:
        return self in (CopilotSessionStatus.DONE, CopilotSessionStatus.FAILED, CopilotSessionStatus.CANCELLED)


class CopilotPlanningTurn(StrEnum):
    """A planning turn handed to the worker: the API saves the user's message
    and answers at once, the worker runs Copilot in plan mode and saves its
    answer. ``None`` on the session = no turn pending (Copilot answered)."""
    QUEUED = "queued"
    """The user's message is saved: waiting for a worker."""
    RUNNING = "running"
    """A worker is running Copilot on it."""


class CopilotMessageRole(StrEnum):
    USER = "user"
    COPILOT = "copilot"
    EVENT = "event"
    """Written by the app: queued, started, finished, warnings."""


class CopilotSession(BaseModel):
    id: int | None = None
    project_name: str
    task_note: str
    """The agent task's note (``agent-task-<title>.md``)."""
    repository: str = ""
    """The only repository chosen (folder inside the project, ``""`` = the
    project folder); ``""`` when several were chosen. Sessions made before
    ``repositories`` have only this."""
    repositories: list[str] = Field(default_factory=list)
    """The repositories Copilot works on (folders inside the project): one = Copilot
    starts in it; more = in the project folder, told which ones. Only these are
    locked during an execution; empty in sessions made before (``repository``)."""
    copilot_session_id: str
    """Copilot's own session (UUID): every turn resumes it."""
    prompt: str = ""
    """The planning prompt chosen when delegating (``coding-agent/<name>.md``); ``""`` = the definition's ``plan_prompt``."""
    model: str = ""
    """Copilot's model, for every turn of the session; ``""`` = COPILOT_MODEL or Copilot's default."""
    status: CopilotSessionStatus = CopilotSessionStatus.PLANNING
    planning_turn: CopilotPlanningTurn | None = None
    """The planning turn waiting for (or in) the worker; None = Copilot answered. Only while ``planning``."""
    cancel_requested: bool = False
    """Set by the API, read by the worker that is running it (an execution or a planning turn)."""
    claimed_by: str | None = None
    """The worker that took the last execution or planning turn; while it beats, a ``running`` one is not orphaned."""
    head_before: str | None = None
    """Sessions made before ``heads_before``: HEAD of ``repository`` when the execution started."""
    head_after: str | None = None
    heads_before: dict[str, str] | None = None
    """HEAD of every repository of the project when the execution started
    (path → commit; ``""`` = no commits yet): all are checked, not only the chosen ones."""
    heads_after: dict[str, str] | None = None
    changed_files: list[str] = Field(default_factory=list)
    """``git status`` of the chosen repositories when the execution ended
    (``<repository>/<path>``; just ``<path>`` for the project folder as repository)."""
    outside_files: list[str] = Field(default_factory=list)
    """Files of the other repositories of the project that changed during the
    execution (they were clean when it started): Copilot was not supposed to touch them."""
    premium_requests: int = 0
    """Copilot's premium requests used by the session so far."""
    error: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @property
    def repos(self) -> list[str]:
        """The repositories Copilot works on (``repository`` for the sessions made before)."""
        return self.repositories or [self.repository]

    @property
    def moved_repositories(self) -> list[str]:
        """The repositories whose HEAD changed during the execution: a commit (or
        a reset, a checkout...) despite the rules. Any of the project, chosen or not."""
        if self.heads_before is not None and self.heads_after is not None:
            return sorted(path for path, head in self.heads_before.items() if path in self.heads_after and self.heads_after[path] != head)
        if self.head_before is not None and self.head_after is not None and self.head_before != self.head_after:
            return [self.repository]
        return []

    @property
    def head_moved(self) -> bool:
        return bool(self.moved_repositories)


class CopilotMessage(BaseModel):
    id: int | None = None
    session_id: int
    role: CopilotMessageRole
    content: str
    created_at: datetime = Field(default_factory=_utc_now)


class CopilotPrice(BaseModel):
    """USD per 1M tokens (1 AI credit = 0.01 USD)."""
    input: float
    cached_input: float
    cache_write: float | None = None
    output: float


class CopilotModel(BaseModel):
    """A model to choose from when delegating, with its price when the definition has one."""
    name: str
    note: str = ""
    price: CopilotPrice | None = None
    long_context_above: int | None = None
    """Input tokens above which ``long_context_price`` applies."""
    long_context_price: CopilotPrice | None = None


class CodingAgentSettings(BaseModel):
    """What the app tells Copilot, from the coding-agent definition files."""
    plan_prompt: str
    """The first planning turn; ``{task}`` becomes the task's markdown."""
    execute_prompt: str
    references_prompt: str = ""
    """Added to the first turn when the task links references; ``{task_folder}``
    = where they are as files. ``""`` = nothing added (Copilot still reads them)."""
    denied_tools: list[str]
    """``--deny-tool`` of the execution, e.g. ``shell(git commit)``."""
    models: list[CopilotModel] = Field(default_factory=list)
    """The models to choose from when delegating (besides the default), as written."""
    prompts: dict[str, str] = Field(default_factory=dict)
    """The planning prompts to choose from instead of ``plan_prompt``: name
    (file name without ``.md``) → text, from ``coding-agent/`` folders."""


class CopilotUsage(BaseModel):
    """Copilot's accounting: of a whole Copilot session so far (what the CLI
    writes with ``--usage-output-file``, cumulative across resumed turns) or of
    one turn (the difference). Copilot bills in AI credits (premium requests on
    the legacy plan), not in tokens × a price: no EUR here."""
    premium_requests: float = 0.0
    nano_aiu: int = 0
    """AI credits × 10⁹ (Copilot's own unit, exact)."""
    input_tokens: int = 0
    """Cached ones included."""
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    api_duration_ms: int = 0

    @property
    def ai_credits(self) -> float:
        return self.nano_aiu / 1e9

    def __add__(self, other: "CopilotUsage") -> "CopilotUsage":
        return CopilotUsage(**{name: getattr(self, name) + getattr(other, name) for name in CopilotUsage.model_fields})

    def since(self, previous: "CopilotUsage") -> "CopilotUsage":
        """What was added after ``previous`` (both cumulative). When a total
        went down Copilot started counting again: all of this is new."""
        if any(getattr(self, name) < getattr(previous, name) for name in CopilotUsage.model_fields):
            return self
        return CopilotUsage(**{name: getattr(self, name) - getattr(previous, name) for name in CopilotUsage.model_fields})


class CopilotTurn(BaseModel):
    """What one invocation of Copilot CLI answered."""
    message: str
    """Copilot's last message ("" when it said nothing)."""
    exit_code: int
    premium_requests: int = 0
    """Used by the whole session so far, as Copilot reports it."""
    error: str | None = None
    """Why the turn failed (exit code, timeout, cancellation), None when it succeeded."""
    cancelled: bool = False
    usage: CopilotUsage | None = None
    """The session's totals after this turn; None when Copilot wrote none (killed, not started)."""
    model: str = ""
    """The model Copilot used last, as it reports it."""


class CopilotPhase(StrEnum):
    PLAN = "plan"
    EXECUTE = "execute"


class CopilotTurnRecord(BaseModel):
    """One turn of a session for observability: what it used. Kept when the
    session is deleted (``session_id`` is a plain number)."""
    id: int | None = None
    session_id: int
    project_name: str
    task_note: str
    phase: CopilotPhase
    model: str = ""
    """The model Copilot reported, else the one asked for; ``""`` = unknown."""
    ok: bool = True
    cancelled: bool = False
    error: str | None = None
    duration_ms: int = 0
    """Wall time of the turn, Copilot's start included."""
    usage: CopilotUsage = Field(default_factory=CopilotUsage)
    created_at: datetime = Field(default_factory=_utc_now)


class CopilotModelUsage(BaseModel):
    """What one model used, over the turns asked for."""
    model: str
    turns: int
    usage: CopilotUsage
