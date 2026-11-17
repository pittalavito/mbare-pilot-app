"""Request/response models of the automation API: pipelines with their steps,
runs, and the tools of the registry (a TOOL step, Admin → Tool)."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from models.domain.pipeline import AutomationPurpose, EdgeConditionKind, Pipeline, PipelineEdge, PipelineRun, PipelineStep
from models.domain.worker import WorkerStatus
from tool.spec import ToolSpec


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
    """``agent`` | ``agent_config`` | ``tool``."""
    input_template: str
    agent: StepAgentBody | None = None
    agent_config_name: str | None = None
    tool_name: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    position_x: float = 0.0
    position_y: float = 0.0
    """Where the node is drawn in the graph editor."""

    def to_step(self) -> PipelineStep:
        return PipelineStep.model_validate(self.model_dump())


class EdgeBody(BaseModel):
    """An edge of the graph, both ways."""
    source: str
    """A step name, or ``input``."""
    target: str
    condition: EdgeConditionKind = EdgeConditionKind.ALWAYS
    """``always`` | ``contains`` | ``not_contains`` | ``matches`` | ``otherwise``."""
    value: str = ""

    def to_edge(self) -> PipelineEdge:
        return PipelineEdge.model_validate(self.model_dump())


class PipelineResponse(BaseModel):
    id: int
    project_name: str
    name: str
    description: str
    active: bool
    steps: list[StepBody]
    edges: list[EdgeBody]
    fields: list[str] = []
    """The named values a run asks for (its input is then a JSON object with them)."""
    purpose: AutomationPurpose = AutomationPurpose.NONE

    @classmethod
    def from_pipeline(cls, pipeline: Pipeline) -> "PipelineResponse":
        return cls(**pipeline.model_dump())


class PipelineRequest(BaseModel):
    """Create and update: the project comes from the URL and never changes."""
    name: str
    description: str = ""
    active: bool = True
    steps: list[StepBody] = Field(default_factory=list)
    edges: list[EdgeBody] = Field(default_factory=list)
    """Empty = the chain of the steps, in their order."""
    fields: list[str] = Field(default_factory=list)
    purpose: AutomationPurpose = AutomationPurpose.NONE


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


_TYPES = {"boolean": "bool", "integer": "int", "number": "float", "string": "str"}


class ToolArgResponse(BaseModel):
    name: str
    type: str
    """``bool`` | ``int`` | ``float`` | ``str`` | ``json`` (a list or an object): the widget the forms show."""
    default: Any = None
    description: str | None = None
    required: bool = False


class ToolSpecResponse(BaseModel):
    """A tool of the registry with its arguments: the editor's form for a tool step, Admin → Tool."""
    name: str
    description: str
    writes: bool
    """It changes something: «Prova» asks first."""
    chatbot_only: bool
    """Only in a chat: not offered for an automation step."""
    args: list[ToolArgResponse]

    @classmethod
    def from_spec(cls, spec: ToolSpec) -> "ToolSpecResponse":
        properties, required = spec.schema()
        args = [
            ToolArgResponse(name=name, type=_TYPES.get(str(field.get("type")), "json" if "type" in field else "str"),
                            default=field.get("default"), description=field.get("description"), required=name in required)
            for name, field in properties.items()
        ]
        return cls(name=spec.name, description=spec.description, writes=spec.writes, chatbot_only=spec.chatbot_only, args=args)


class ToolTryRequest(BaseModel):
    project: str
    args: dict[str, Any] = {}


class ToolTryResponse(BaseModel):
    """What «▶️ Prova» got: the result as an agent sees it (JSON) and as a step outputs it (text)."""
    ok: bool
    text: str
    """The step's output: the result's ``text``, else its JSON."""
    result: dict[str, Any]
    error: str | None = None


class WorkerResponse(BaseModel):
    worker_id: str
    host: str
    pid: int
    started_at: datetime
    last_seen: datetime
    busy_run_id: int | None
    """The run being executed; None = waiting for the queue."""
    busy_copilot_session_id: int | None = None
    """The Copilot session being executed."""

    @classmethod
    def from_status(cls, status: WorkerStatus) -> "WorkerResponse":
        return cls(**status.model_dump())
