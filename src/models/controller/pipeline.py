"""Request/response models of the automation API: pipelines with their steps,
runs, and the functions a FUNCTION step can call."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from function.spec import FunctionSpec
from models.domain.pipeline import Pipeline, PipelineRun, PipelineStep
from models.domain.worker import WorkerStatus


class StepAgentBody(BaseModel):
    system_prompt: str
    prompt_version: int = 1
    model: str
    max_steps: int = 4
    tool_names: list[str] = Field(default_factory=list)


class StepBody(BaseModel):
    """A step, both ways. ``id`` None = a new step."""
    id: int | None = None
    name: str
    kind: str
    """``agent`` | ``agent_config`` | ``function``."""
    input_template: str
    agent: StepAgentBody | None = None
    agent_config_name: str | None = None
    function_name: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)

    def to_step(self) -> PipelineStep:
        return PipelineStep.model_validate(self.model_dump())


class PipelineResponse(BaseModel):
    id: int
    project_name: str
    name: str
    description: str
    active: bool
    steps: list[StepBody]

    @classmethod
    def from_pipeline(cls, pipeline: Pipeline) -> "PipelineResponse":
        return cls(**pipeline.model_dump())


class PipelineRequest(BaseModel):
    """Create and update: the project comes from the URL and never changes."""
    name: str
    description: str = ""
    active: bool = True
    steps: list[StepBody] = Field(default_factory=list)


class StepRunResponse(BaseModel):
    position: int
    name: str
    kind: str
    status: str
    input: str
    output: str | None
    error: str | None
    agent_run_id: str | None
    started_at: datetime | None
    finished_at: datetime | None


class RunResponse(BaseModel):
    id: int
    pipeline_id: int
    status: str
    """``queued`` | ``running`` | ``done`` | ``failed``."""
    input: str
    output: str | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    steps: list[StepRunResponse]

    @classmethod
    def from_run(cls, run: PipelineRun) -> "RunResponse":
        return cls(**run.model_dump())


class RunRequest(BaseModel):
    input: str = ""


class FunctionParamResponse(BaseModel):
    name: str
    type: str
    """``bool`` | ``int`` | ``float`` | ``str``: the widget the editor shows."""
    default: Any = None
    description: str | None = None


class FunctionResponse(BaseModel):
    name: str
    description: str
    params: list[FunctionParamResponse]

    @classmethod
    def from_spec(cls, spec: FunctionSpec) -> "FunctionResponse":
        params = [
            FunctionParamResponse(
                name=name,
                type=info.annotation.__name__ if info.annotation in (bool, int, float) else "str",
                default=None if info.is_required() else info.default,
                description=info.description,
            )
            for name, info in spec.params.model_fields.items()
        ]
        return cls(name=spec.name, description=spec.description, params=params)


class WorkerResponse(BaseModel):
    worker_id: str
    host: str
    pid: int
    started_at: datetime
    last_seen: datetime
    busy_run_id: int | None
    """The run being executed; None = waiting for the queue."""

    @classmethod
    def from_status(cls, status: WorkerStatus) -> "WorkerResponse":
        return cls(**status.model_dump())
