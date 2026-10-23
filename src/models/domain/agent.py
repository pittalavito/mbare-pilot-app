from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from models.domain.chat import ModelKey

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
"""A required identifier: trimmed, non-empty."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- definitions

class AgentRole(BaseModel):
    """What an agent is for (e.g. ``hello``, ``reviewer``). Prompts and
    configurations belong to a role. Roles are never deleted: an inactive role
    cannot be picked by configurations, and its configurations cannot run.
    ``project_name`` None = global (usable by every project)."""
    name: Name
    project_name: str | None = None
    description: str = ""
    active: bool = True


class SystemPrompt(BaseModel):
    """One immutable version of a role's system prompt. Editing a prompt
    creates version ``n+1``; configurations point at a specific version. The
    text never changes; only ``active`` can be toggled (versions are never
    deleted: an inactive version cannot be picked, and configurations pinned to
    it cannot run)."""
    id: int | None = None
    role_name: Name
    version: int = Field(ge=1)
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    active: bool = True
    created_at: datetime = Field(default_factory=_utc_now)


class ToolInfo(BaseModel):
    """A tool in the catalog. The implementation lives in code
    (tool/registry.py); ``available`` is False when a catalogued tool is no
    longer implemented, so it cannot be used."""
    name: Name
    description: str = ""
    available: bool = True


class AgentConfig(BaseModel):
    """A runnable agent: role + pinned prompt version + model + tools.
    ``project_name`` None = global (usable by every project)."""
    name: Name
    project_name: str | None = None
    description: str = ""
    role_name: Name
    prompt_id: int
    model: ModelKey
    max_steps: int = Field(default=4, ge=1, le=50)
    tool_names: list[str] = Field(default_factory=list)


class AgentSpec(BaseModel):
    """A configuration resolved with its prompt text, ready to build an agent."""
    config: AgentConfig
    prompt: SystemPrompt


class AgentDefinition(BaseModel):
    """Everything AgentService needs to build, run and record one agent,
    whatever it comes from: an agent configuration or a chatbot."""
    name: str
    """Recorded as the run's ``config_name``."""
    role_name: str
    prompt_id: int
    """0 when the prompt is not a SystemPrompt row (e.g. a chatbot's own prompt)."""
    prompt_version: int
    system_prompt: str
    model: ModelKey
    max_steps: int
    tool_names: list[str] = Field(default_factory=list)
    project_name: str | None = None
    """Project the agent belongs to (None = global): its runs default to it."""

    @classmethod
    def from_spec(cls, spec: AgentSpec) -> "AgentDefinition":
        return cls(
            name=spec.config.name,
            role_name=spec.config.role_name,
            prompt_id=spec.prompt.id,
            prompt_version=spec.prompt.version,
            system_prompt=spec.prompt.text,
            model=spec.config.model,
            max_steps=spec.config.max_steps,
            tool_names=list(spec.config.tool_names),
            project_name=spec.config.project_name,
        )


# ----------------------------------------------------------------------- runs

class RunOrigin(StrEnum):
    """What triggered an agent run."""
    CHAT = "chat"
    PIPELINE = "pipeline"
    MANUAL = "manual"



class TokenSummary(BaseModel):
    """Token usage and cost of one or more LLM generations."""
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    thinking_tokens: int = 0
    cost_eur: float = 0.0

    def __add__(self, other: "TokenSummary") -> "TokenSummary":
        return TokenSummary(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cached_tokens=self.cached_tokens + other.cached_tokens,
            thinking_tokens=self.thinking_tokens + other.thinking_tokens,
            cost_eur=round(self.cost_eur + other.cost_eur, 6),
        )


class GenerationRecord(BaseModel):
    """One LLM call (datapizza ``generation`` span). ``tool_name`` is set when
    the call happened inside a tool, None when it was the agent's own call."""
    model: str
    tokens: TokenSummary
    latency_ms: float
    tool_name: str | None = None


class ToolCallRecord(BaseModel):
    """One tool execution (datapizza ``tool`` span), with the tokens of the
    LLM calls made inside it."""
    name: str
    arguments: str = ""
    result: str | None = None
    ok: bool = True
    error: str | None = None
    latency_ms: float = 0.0
    tokens: TokenSummary = Field(default_factory=TokenSummary)


class RunTelemetry(BaseModel):
    """Everything datapizza traced during one run, aggregated."""
    agent_tokens: TokenSummary = Field(default_factory=TokenSummary)
    tool_tokens: TokenSummary = Field(default_factory=TokenSummary)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    generations: list[GenerationRecord] = Field(default_factory=list)

    @property
    def total_tokens(self) -> TokenSummary:
        return self.agent_tokens + self.tool_tokens


class AgentRunRecord(BaseModel):
    """A full agent run: facts (persisted in SQL) plus the verbatim trace
    (input, output, tool calls, generations — persisted in Redis)."""
    run_id: str
    project_name: str | None = None
    origin: RunOrigin = RunOrigin.MANUAL
    config_name: str
    role_name: str
    prompt_id: int
    prompt_version: int
    model: str
    ok: bool = True
    error: str | None = None
    latency_ms: float = 0.0
    created_at: datetime = Field(default_factory=_utc_now)
    input: str = ""
    output: str = ""
    telemetry: RunTelemetry = Field(default_factory=RunTelemetry)


class AgentRunSummary(BaseModel):
    """The facts of one run, without the verbatim trace."""
    run_id: str
    project_name: str | None = None
    origin: str
    config_name: str
    role_name: str
    prompt_version: int
    model: str
    ok: bool
    error: str | None = None
    latency_ms: float
    agent_tokens: TokenSummary
    tool_tokens: TokenSummary
    total_tokens: TokenSummary
    tool_names: list[str]
    created_at: datetime


class ToolCallSummary(BaseModel):
    """The facts of one tool call."""
    run_id: str
    tool_name: str
    ok: bool
    error: str | None = None
    latency_ms: float
    tokens: TokenSummary
    created_at: datetime
