"""Automation domain models: a project's pipelines (ordered steps, each output
feeding the next) and their runs, executed by the worker."""
from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, Field, StringConstraints

from models.domain.agent import Name
from models.domain.chat import ModelKey

INPUT = "{input}"
"""Placeholder of the previous step's output (the run input for the first step)."""
PIPELINE_INPUT = "{pipeline_input}"
"""Placeholder of the run input, in every step."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StepKind(StrEnum):
    AGENT = "agent"
    """Its own agent, configured in the step (like a chatbot's)."""
    AGENT_CONFIG = "agent_config"
    """An agent of the Library (global or of the project)."""
    FUNCTION = "function"
    """A Python function implemented in code (no LLM)."""


class StepAgent(BaseModel):
    """The own agent of an AGENT step."""
    system_prompt: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    prompt_version: int = Field(default=1, ge=1)
    """Incremented whenever the system prompt changes."""
    model: ModelKey
    max_steps: int = Field(default=4, ge=1, le=50)
    tool_names: list[str] = Field(default_factory=list)


class PipelineStep(BaseModel):
    id: int | None = None
    """None for a step not saved yet."""
    name: Name
    kind: StepKind
    input_template: str = INPUT
    """What the step receives: ``{input}`` and ``{pipeline_input}`` are replaced."""
    agent: StepAgent | None = None
    """AGENT steps only."""
    agent_config_name: str | None = None
    """AGENT_CONFIG steps only."""
    function_name: str | None = None
    """FUNCTION steps only."""
    params: dict[str, Any] = Field(default_factory=dict)
    """FUNCTION steps only."""

    def render_input(self, previous_output: str, pipeline_input: str) -> str:
        return self.input_template.replace(PIPELINE_INPUT, pipeline_input).replace(INPUT, previous_output)


class Pipeline(BaseModel):
    id: int | None = None
    project_name: str
    name: Name
    description: str = ""
    active: bool = True
    steps: list[PipelineStep] = Field(default_factory=list)
    """In execution order."""
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"

    @property
    def finished(self) -> bool:
        return self in (RunStatus.DONE, RunStatus.FAILED)


class PipelineStepRun(BaseModel):
    id: int | None = None
    pipeline_run_id: int
    step_id: int | None = None
    """None once the step is deleted from the pipeline."""
    position: int
    name: str
    kind: StepKind
    status: RunStatus = RunStatus.RUNNING
    input: str = ""
    output: str | None = None
    error: str | None = None
    agent_run_id: str | None = None
    """The agent run of an AGENT / AGENT_CONFIG step (costs, trace)."""
    started_at: datetime | None = None
    finished_at: datetime | None = None


class PipelineRun(BaseModel):
    id: int | None = None
    pipeline_id: int
    status: RunStatus = RunStatus.QUEUED
    input: str = ""
    output: str | None = None
    """The last step's output, once DONE."""
    error: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    steps: list[PipelineStepRun] = Field(default_factory=list)
    """Filled when read with its steps."""
