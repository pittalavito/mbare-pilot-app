"""Automation domain models: a project's pipelines, a graph of steps (the
edges say which output feeds which step, on which condition), and their runs,
executed by the worker. Graph rules in domain/pipeline/graph.py."""
import json
import re
from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, Field, StringConstraints

from core.error import ValidationError
from models.domain.agent import Name
from models.domain.chat import ModelKey

INPUT = "{input}"
"""Placeholder of the previous step's output (the run input for the first step)."""
PIPELINE_INPUT = "{pipeline_input}"
"""Placeholder of the run input, in every step."""
NODE_PLACEHOLDER = re.compile(r"\{nodo:([^}]+)\}")
"""``{nodo:Name}``: the output of the step ``Name`` (one that comes before)."""
INPUT_NODE = "input"
"""The node of the run input: every graph starts here; no step may be called so."""
FIELD_PLACEHOLDER = re.compile(r"\{in:([a-z][a-z0-9_]*)\}")
"""``{in:branch}``: the value of a field of the run (an automation with ``fields``)."""
FieldName = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[a-z][a-z0-9_]*$", max_length=40)]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StepKind(StrEnum):
    AGENT = "agent"
    """Its own agent, configured in the step (like a chatbot's)."""
    AGENT_CONFIG = "agent_config"
    """An agent of the Library (global or of the project)."""
    FUNCTION = "function"
    """A Python function implemented in code (no LLM)."""
    TOOL = "tool"
    """An agent's tool called with fixed arguments (no LLM): what an Operator did,
    promoted to an automation (plan 11). Its arguments can use ``{in:field}``."""


class AutomationPurpose(StrEnum):
    """Where the app offers an automation by itself (plan 11), besides the list."""
    NONE = ""
    PREPARE = "prepare"
    """The preparation before Copilot: offered in the delegation, its fields filled from the task."""


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
    tool_name: str | None = None
    """TOOL steps only."""
    params: dict[str, Any] = Field(default_factory=dict)
    """FUNCTION steps: the function's parameters; TOOL steps: the tool's arguments."""
    position_x: float = 0.0
    position_y: float = 0.0
    """Where the node is drawn in the graph editor."""

    def render_input(self, previous_output: str, pipeline_input: str, node_outputs: dict[str, str] | None = None,
                     fields: dict[str, str] | None = None) -> str:
        """The template with ``{pipeline_input}``, ``{nodo:Name}`` (empty for a
        node that did not run), ``{in:field}`` and ``{input}`` replaced."""
        outputs = node_outputs or {}
        text = fill_fields(self.input_template, fields or {})
        text = text.replace(PIPELINE_INPUT, pipeline_input)
        text = NODE_PLACEHOLDER.sub(lambda match: outputs.get(match.group(1), ""), text)
        return text.replace(INPUT, previous_output)


def fill_fields(value: Any, fields: dict[str, str]) -> Any:
    """``value`` with every ``{in:field}`` replaced, also inside lists and dicts (a tool's arguments)."""
    if isinstance(value, str):
        return FIELD_PLACEHOLDER.sub(lambda match: fields.get(match.group(1), match.group(0)), value)
    if isinstance(value, dict):
        return {key: fill_fields(item, fields) for key, item in value.items()}
    if isinstance(value, list):
        return [fill_fields(item, fields) for item in value]
    return value


def used_fields(value: Any) -> set[str]:
    """The fields ``value`` names with ``{in:field}`` (also inside lists and dicts)."""
    if isinstance(value, str):
        return set(FIELD_PLACEHOLDER.findall(value))
    if isinstance(value, dict):
        return set().union(*(used_fields(item) for item in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(used_fields(item) for item in value)) if value else set()
    return set()


class EdgeConditionKind(StrEnum):
    """When an edge lets the source's output through to its target."""
    ALWAYS = "always"
    CONTAINS = "contains"
    """The output contains ``value`` (case-insensitive)."""
    NOT_CONTAINS = "not_contains"
    MATCHES = "matches"
    """The output matches the regex ``value``."""
    OTHERWISE = "otherwise"
    """None of the text conditions leaving the same node is true."""


class PipelineEdge(BaseModel):
    source: Annotated[str, StringConstraints(strip_whitespace=True)]
    """A step name, or ``input``."""
    target: Annotated[str, StringConstraints(strip_whitespace=True)]
    """A step name."""
    condition: EdgeConditionKind = EdgeConditionKind.ALWAYS
    value: str = ""
    """The text (or regex) of the condition."""


class Pipeline(BaseModel):
    id: int | None = None
    project_name: str
    name: Name
    description: str = ""
    active: bool = True
    steps: list[PipelineStep] = Field(default_factory=list)
    """The nodes; their order breaks ties in the execution order."""
    edges: list[PipelineEdge] = Field(default_factory=list)
    fields: list[FieldName] = Field(default_factory=list)
    """The named values a run receives (plan 11), used by the steps as ``{in:field}``:
    the run input is then a JSON object with them (``run_fields``)."""
    purpose: AutomationPurpose = AutomationPurpose.NONE
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

    def run_fields(self, run_input: str) -> dict[str, str]:
        """The fields' values from a run input (a JSON object); ValidationError
        naming what is missing. ``{}`` for an automation without fields."""
        if not self.fields:
            return {}
        try:
            raw = json.loads(run_input or "{}")
        except json.JSONDecodeError as exc:
            raise ValidationError(f"L'automation {self.name} vuole i campi {', '.join(self.fields)} come oggetto JSON.") from exc
        if not isinstance(raw, dict):
            raise ValidationError(f"L'automation {self.name} vuole i campi {', '.join(self.fields)} come oggetto JSON.")
        values = {name: str(raw.get(name) or "").strip() for name in self.fields}
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise ValidationError(f"Manca il valore di: {', '.join(missing)}.")
        return values


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"
    """Steps only: no edge into the step let anything through."""

    @property
    def finished(self) -> bool:
        return self in (RunStatus.DONE, RunStatus.FAILED, RunStatus.SKIPPED)


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
