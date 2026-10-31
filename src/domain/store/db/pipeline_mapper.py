"""Automations: domain pipelines (steps, edges) and runs (step runs) <->
``pipeline`` / ``pipeline_step`` / ``pipeline_edge`` / ``pipeline_run`` /
``pipeline_step_run`` rows. Edges point to steps by id in the DB and by name in
the domain: the mapper translates."""
from domain.store.db.mapper import as_utc
from models.domain.pipeline import (
    INPUT_NODE,
    EdgeConditionKind,
    Pipeline,
    PipelineEdge,
    PipelineRun,
    PipelineStep,
    PipelineStepRun,
    RunStatus,
    StepAgent,
    StepKind,
)
from models.store.db import PipelineEdgeTable, PipelineRunTable, PipelineStepRunTable, PipelineStepTable, PipelineTable


class Adapter:
    """Read seam: DB rows -> domain models."""

    @staticmethod
    def to_pipeline(row: PipelineTable, step_rows: list[PipelineStepTable],
                    edge_rows: list[PipelineEdgeTable] | None = None) -> Pipeline:
        names = {step_row.id: step_row.name for step_row in step_rows}
        return Pipeline(
            id=row.id,
            project_name=row.project_name,
            name=row.name,
            description=row.description,
            active=row.active,
            steps=[Adapter.to_pipeline_step(step_row) for step_row in step_rows],
            edges=[
                PipelineEdge(
                    source=INPUT_NODE if edge_row.source_step_id is None else names[edge_row.source_step_id],
                    target=names[edge_row.target_step_id],
                    condition=EdgeConditionKind(edge_row.condition), value=edge_row.value,
                )
                for edge_row in edge_rows or []
                if edge_row.target_step_id in names and (edge_row.source_step_id is None or edge_row.source_step_id in names)
            ],
            created_at=as_utc(row.created_at),
            updated_at=as_utc(row.updated_at),
        )

    @staticmethod
    def to_pipeline_step(row: PipelineStepTable) -> PipelineStep:
        kind = StepKind(row.kind)
        agent = None
        if kind is StepKind.AGENT:
            agent = StepAgent(
                system_prompt=row.system_prompt or "",
                prompt_version=row.prompt_version,
                model=row.model or "",
                max_steps=row.max_steps or 4,
                tool_names=list(row.tool_names),
            )
        return PipelineStep(
            id=row.id,
            name=row.name,
            kind=kind,
            input_template=row.input_template,
            agent=agent,
            agent_config_name=row.agent_config_name,
            function_name=row.function_name,
            params=dict(row.params),
            position_x=row.position_x,
            position_y=row.position_y,
        )

    @staticmethod
    def to_pipeline_run(row: PipelineRunTable, step_rows: list[PipelineStepRunTable] | None = None) -> PipelineRun:
        return PipelineRun(
            id=row.id,
            pipeline_id=row.pipeline_id,
            status=RunStatus(row.status),
            input=row.input,
            output=row.output,
            error=row.error,
            created_at=as_utc(row.created_at),
            started_at=as_utc(row.started_at) if row.started_at else None,
            finished_at=as_utc(row.finished_at) if row.finished_at else None,
            steps=[Adapter.to_pipeline_step_run(step_row) for step_row in step_rows or []],
        )

    @staticmethod
    def to_pipeline_step_run(row: PipelineStepRunTable) -> PipelineStepRun:
        step_run = PipelineStepRun.model_validate(row.model_dump())
        step_run.started_at = as_utc(step_run.started_at) if step_run.started_at else None
        step_run.finished_at = as_utc(step_run.finished_at) if step_run.finished_at else None
        return step_run


class Factory:
    """Write seam: domain models -> DB rows."""

    @staticmethod
    def to_pipeline_row(pipeline: Pipeline) -> PipelineTable:
        return PipelineTable(**pipeline.model_dump(exclude={"steps", "edges"}))

    @staticmethod
    def to_pipeline_step_row(step: PipelineStep, pipeline_id: int, position: int) -> PipelineStepTable:
        agent = step.agent
        return PipelineStepTable(
            id=step.id,
            pipeline_id=pipeline_id,
            position=position,
            name=step.name,
            kind=step.kind.value,
            input_template=step.input_template,
            system_prompt=agent.system_prompt if agent else None,
            prompt_version=agent.prompt_version if agent else 1,
            model=agent.model if agent else None,
            max_steps=agent.max_steps if agent else None,
            tool_names=list(agent.tool_names) if agent else [],
            agent_config_name=step.agent_config_name,
            function_name=step.function_name,
            params=dict(step.params),
            position_x=step.position_x,
            position_y=step.position_y,
        )

    @staticmethod
    def to_pipeline_edge_row(edge: PipelineEdge, pipeline_id: int, step_ids: dict[str, int]) -> PipelineEdgeTable:
        """``step_ids``: the saved steps' ids by name."""
        return PipelineEdgeTable(
            pipeline_id=pipeline_id,
            source_step_id=None if edge.source == INPUT_NODE else step_ids[edge.source],
            target_step_id=step_ids[edge.target],
            condition=edge.condition.value,
            value=edge.value,
        )

    @staticmethod
    def to_pipeline_run_row(run: PipelineRun) -> PipelineRunTable:
        return PipelineRunTable(**{**run.model_dump(exclude={"steps"}), "status": run.status.value})

    @staticmethod
    def to_pipeline_step_run_row(step_run: PipelineStepRun) -> PipelineStepRunTable:
        return PipelineStepRunTable(
            **{**step_run.model_dump(), "kind": step_run.kind.value, "status": step_run.status.value},
        )
