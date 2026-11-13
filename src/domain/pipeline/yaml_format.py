"""An automation as YAML, in the format of the definitions
(``global-automation.yml``, ``automation.yml``): read (the Architect's
proposals, «Salva» in the chat), written («Esporta YAML») and turned into
steps and edges (also by the definitions' sync). Pure functions.

A proposal is one automation: its fields at the top level, or the usual file
with ``automations:`` and exactly one element."""
from typing import Any

import yaml
from pydantic import ValidationError as PydanticValidationError

from core.error import ValidationError
from models.domain.definitions import AutomationFile, StepFile
from models.domain.pipeline import INPUT, EdgeConditionKind, Pipeline, PipelineEdge, PipelineStep, StepAgent, StepKind


def parse(text: str) -> AutomationFile:
    """ValidationError with what is wrong, in words (YAML, fields)."""
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValidationError(f"YAML non valido: {exc}") from exc
    if isinstance(raw, dict) and "automations" in raw:
        items = raw["automations"]
        if not isinstance(items, list) or len(items) != 1:
            raise ValidationError("Scrivi una sola automation (sotto automations: un elemento solo).")
        raw = items[0]
    if not isinstance(raw, dict):
        raise ValidationError("L'automation deve essere un oggetto con name, steps e (facoltativi) description, edges, fields, purpose.")
    try:
        return AutomationFile.model_validate(raw)
    except PydanticValidationError as exc:
        error = exc.errors()[0]
        where = ".".join(str(part) for part in error["loc"])
        raise ValidationError(f"{where}: {error['msg']}" if where else error["msg"]) from exc


def step_from_file(spec: StepFile, previous: PipelineStep | None = None) -> PipelineStep:
    """A step of the file; ``previous`` (same name) keeps its id and its place in the graph editor."""
    common: dict[str, Any] = dict(
        id=previous.id if previous else None,
        name=spec.name,
        input_template=spec.input,
        position_x=previous.position_x if previous else 0.0,
        position_y=previous.position_y if previous else 0.0,
    )
    if spec.function is not None:
        return PipelineStep(kind=StepKind.FUNCTION, function_name=spec.function, params=spec.params, **common)
    if spec.tool is not None:
        return PipelineStep(kind=StepKind.TOOL, tool_name=spec.tool, params=spec.args, **common)
    if spec.agent is not None:
        return PipelineStep(kind=StepKind.AGENT_CONFIG, agent_config_name=spec.agent, **common)
    assert spec.system_prompt is not None and spec.model is not None  # StepFile checks it: an own agent has both
    agent = StepAgent(system_prompt=spec.system_prompt, model=spec.model, max_steps=spec.max_steps, tool_names=spec.tools)
    return PipelineStep(kind=StepKind.AGENT, agent=agent, **common)


def steps_and_edges(spec: AutomationFile, current: Pipeline | None = None) -> tuple[list[PipelineStep], list[PipelineEdge]]:
    """The steps (matched by name with ``current``'s) and the edges written (empty = the chain)."""
    previous = {step.name.lower(): step for step in current.steps} if current else {}
    steps = [step_from_file(step, previous.get(step.name.lower())) for step in spec.steps]
    edges = [PipelineEdge(source=edge.source, target=edge.target, condition=edge.condition, value=edge.value) for edge in spec.edges or []]
    return steps, edges


def to_file(pipeline: Pipeline) -> dict[str, Any]:
    """The automation as an element of ``automations:`` (only what is not the default)."""
    item: dict[str, Any] = {"name": pipeline.name}
    if pipeline.description:
        item["description"] = pipeline.description
    if not pipeline.active:
        item["active"] = False
    if pipeline.purpose:
        item["purpose"] = pipeline.purpose.value
    if pipeline.fields:
        item["fields"] = list(pipeline.fields)
    item["steps"] = [_step_to_file(step) for step in pipeline.steps]
    if pipeline.edges:
        item["edges"] = [_edge_to_file(edge) for edge in pipeline.edges]
    return item


def dump(pipeline: Pipeline) -> str:
    """The text to paste under ``automations:`` of a definitions file."""
    return yaml.safe_dump({"automations": [to_file(pipeline)]}, sort_keys=False, allow_unicode=True, width=120)


def _step_to_file(step: PipelineStep) -> dict[str, Any]:
    item: dict[str, Any] = {"name": step.name}
    if step.input_template != INPUT:
        item["input"] = step.input_template
    if step.kind is StepKind.FUNCTION:
        item["function"] = step.function_name
        if step.params:
            item["params"] = dict(step.params)
    elif step.kind is StepKind.TOOL:
        item["tool"] = step.tool_name
        if step.params:
            item["args"] = dict(step.params)
    elif step.kind is StepKind.AGENT_CONFIG:
        item["agent"] = step.agent_config_name
    elif step.agent is not None:
        item |= {"system_prompt": step.agent.system_prompt, "model": step.agent.model}
        if step.agent.max_steps != 4:
            item["max_steps"] = step.agent.max_steps
        if step.agent.tool_names:
            item["tools"] = list(step.agent.tool_names)
    return item


def _edge_to_file(edge: PipelineEdge) -> dict[str, Any]:
    item: dict[str, Any] = {"from": edge.source, "to": edge.target}
    if edge.condition is not EdgeConditionKind.ALWAYS:
        item["if"] = edge.condition.value
        if edge.value:
            item["value"] = edge.value
    return item
