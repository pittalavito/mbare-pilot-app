"""Agent tasks delegated to GitHub Copilot CLI. A session is a conversation
with Copilot about one task on one repository of the project: first the
planning chat (Copilot reads the code and asks questions, it cannot change
anything), then, after the user's ok, the execution in the worker (Copilot
changes files, never commits). Copilot keeps the conversation itself
(``copilot_session_id``); the app keeps the messages to show them."""
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CopilotSessionStatus(StrEnum):
    PLANNING = "planning"
    """The chat before the ok: each message is a turn in plan mode (read only)."""
    QUEUED = "queued"
    """Ok given: waiting for the worker (one execution at a time per repository)."""
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def finished(self) -> bool:
        return self in (CopilotSessionStatus.DONE, CopilotSessionStatus.FAILED, CopilotSessionStatus.CANCELLED)


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
    """Folder of the repository inside the project (``""`` = the project folder)."""
    copilot_session_id: str
    """Copilot's own session (UUID): every turn resumes it."""
    prompt: str = ""
    """The planning prompt chosen when delegating (``coding-agent/<name>.md``); ``""`` = the definition's ``plan_prompt``."""
    model: str = ""
    """Copilot's model, for every turn of the session; ``""`` = COPILOT_MODEL or Copilot's default."""
    status: CopilotSessionStatus = CopilotSessionStatus.PLANNING
    cancel_requested: bool = False
    """Set by the API, read by the worker that is running it."""
    head_before: str | None = None
    """HEAD when the execution started; ``""`` = the repository had no commits."""
    head_after: str | None = None
    changed_files: list[str] = Field(default_factory=list)
    """``git status`` of the repository when the execution ended."""
    premium_requests: int = 0
    """Copilot's premium requests used by the session so far."""
    error: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @property
    def head_moved(self) -> bool:
        """A commit (or a reset, a checkout...) happened during the execution, despite the rules."""
        return self.head_before is not None and self.head_after is not None and self.head_before != self.head_after


class CopilotMessage(BaseModel):
    id: int | None = None
    session_id: int
    role: CopilotMessageRole
    content: str
    created_at: datetime = Field(default_factory=_utc_now)


class CodingAgentSettings(BaseModel):
    """What the app tells Copilot, from the coding-agent definition files."""
    plan_prompt: str
    """The first planning turn; ``{task}`` becomes the task's markdown."""
    execute_prompt: str
    denied_tools: list[str]
    """``--deny-tool`` of the execution, e.g. ``shell(git commit)``."""
    models: list[str] = Field(default_factory=list)
    """The models to choose from when delegating (besides the default)."""
    prompts: dict[str, str] = Field(default_factory=dict)
    """The planning prompts to choose from instead of ``plan_prompt``: name
    (file name without ``.md``) → text, from ``coding-agent/`` folders."""


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
