"""Request/response models of the Copilot API: agent tasks delegated to GitHub Copilot CLI."""
from datetime import datetime

from pydantic import BaseModel

from models.domain.copilot import CopilotMessage, CopilotModel, CopilotModelUsage, CopilotSession, CopilotTurnRecord, CopilotUsage


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
    planning_turn: str | None
    """While ``planning``: ``queued`` (the message waits for a worker) | ``running`` (Copilot is answering) | null (Copilot answered)."""
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
    models: list["CopilotModelOptionResponse"] = []
    """Models to choose from besides the default, the cheapest first."""
    default_model: str = ""
    """COPILOT_MODEL; ``""`` = Copilot's own default."""


class CopilotUsageResponse(BaseModel):
    """Copilot's accounting: AI credits (premium requests on the legacy plan) and tokens; no EUR."""
    premium_requests: float
    ai_credits: float
    input_tokens: int
    """Cached ones included."""
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    reasoning_tokens: int
    api_duration_ms: int

    @classmethod
    def from_usage(cls, usage: CopilotUsage) -> "CopilotUsageResponse":
        return cls(**usage.model_dump(exclude={"nano_aiu"}), ai_credits=round(usage.ai_credits, 4))


class CopilotTurnResponse(BaseModel):
    id: int
    session_id: int
    project_name: str
    task_note: str
    phase: str
    """``plan`` | ``execute``."""
    model: str
    ok: bool
    cancelled: bool
    error: str | None
    duration_ms: int
    usage: CopilotUsageResponse
    created_at: datetime

    @classmethod
    def from_turn(cls, turn: CopilotTurnRecord) -> "CopilotTurnResponse":
        return cls(**turn.model_dump(exclude={"usage"}), usage=CopilotUsageResponse.from_usage(turn.usage))


class CopilotSessionUsageResponse(BaseModel):
    """A session's turns and their sum."""
    total: CopilotUsageResponse
    turns: list[CopilotTurnResponse]

    @classmethod
    def from_turns(cls, turns: list[CopilotTurnRecord]) -> "CopilotSessionUsageResponse":
        total = sum((turn.usage for turn in turns), CopilotUsage())
        return cls(total=CopilotUsageResponse.from_usage(total), turns=[CopilotTurnResponse.from_turn(turn) for turn in turns])


class CopilotModelUsageResponse(BaseModel):
    model: str
    """``""`` = unknown (Copilot reported none)."""
    turns: int
    usage: CopilotUsageResponse

    @classmethod
    def from_model_usage(cls, item: CopilotModelUsage) -> "CopilotModelUsageResponse":
        return cls(model=item.model, turns=item.turns, usage=CopilotUsageResponse.from_usage(item.usage))


class CopilotPriceResponse(BaseModel):
    """USD per 1M tokens (1 AI credit = 0.01 USD)."""
    input: float
    cached_input: float
    cache_write: float | None
    output: float


class CopilotModelOptionResponse(BaseModel):
    """A model to choose from when delegating: its price (from the
    coding-agent definition) and what it actually cost so far."""
    name: str
    note: str
    price: CopilotPriceResponse | None
    long_context_above: int | None
    long_context_price: CopilotPriceResponse | None
    turns: int
    """Turns recorded with this model, every project."""
    average_ai_credits: float | None
    """AI credits per turn on average; None = never used."""

    @classmethod
    def from_option(cls, model: CopilotModel, usage: CopilotModelUsage | None) -> "CopilotModelOptionResponse":
        turns = usage.turns if usage else 0
        return cls(
            **model.model_dump(), turns=turns,
            average_ai_credits=round(usage.usage.ai_credits / turns, 4) if usage and turns else None,
        )


CopilotStatusResponse.model_rebuild()


class CopilotDeletedResponse(BaseModel):
    deleted: int
    """How many sessions were deleted."""
