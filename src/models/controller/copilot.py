"""Request/response models of the Copilot API: agent tasks delegated to GitHub Copilot CLI."""
from datetime import datetime

from pydantic import BaseModel

from models.domain.copilot import CopilotMessage, CopilotSession


class CopilotSessionRequest(BaseModel):
    task_note: str
    """The agent task's note (``agent-task-<title>.md``)."""
    repository: str = ""
    """Folder of the repository inside the project (``""`` = the project folder)."""
    prompt: str = ""
    """One of the status' ``prompts``; ``""`` = the definition's ``plan_prompt``."""
    model: str = ""
    """One of the status' ``models``; ``""`` = the default."""


class CopilotMessageRequest(BaseModel):
    text: str


class CopilotSessionResponse(BaseModel):
    id: int
    project_name: str
    task_note: str
    repository: str
    prompt: str
    """The planning prompt chosen; ``""`` = the default."""
    model: str
    """``""`` = the default."""
    status: str
    """``planning`` | ``queued`` | ``running`` | ``done`` | ``failed`` | ``cancelled``."""
    cancel_requested: bool
    head_before: str | None
    head_after: str | None
    head_moved: bool
    """HEAD changed during the execution: a commit (or similar) despite the rules."""
    changed_files: list[str]
    premium_requests: int
    error: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def from_session(cls, session: CopilotSession) -> "CopilotSessionResponse":
        return cls(**session.model_dump(exclude={"copilot_session_id"}), head_moved=session.head_moved)


class CopilotMessageResponse(BaseModel):
    id: int
    role: str
    """``user`` | ``copilot`` | ``event`` (written by the app)."""
    content: str
    created_at: datetime

    @classmethod
    def from_message(cls, message: CopilotMessage) -> "CopilotMessageResponse":
        return cls(**message.model_dump(exclude={"session_id"}))


class CopilotStatusResponse(BaseModel):
    installed: bool
    version: str | None
    definition_error: str | None = None
    """Why the coding-agent definition (prompts, denied tools) cannot be used; None when fine."""
    prompts: list[str] = []
    """Planning prompts to choose from besides the default (``coding-agent/<name>.md``)."""
    models: list[str] = []
    """Models to choose from besides the default."""
    default_model: str = ""
    """COPILOT_MODEL; ``""`` = Copilot's own default."""
