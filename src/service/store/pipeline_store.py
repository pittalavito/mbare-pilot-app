"""The automations: pipelines with their steps and edges, and their runs with
the step runs. A pipeline is saved whole (steps and edges replaced in one
transaction), so the store keeps the engine for its unit of work."""
from sqlalchemy.engine import Engine

from domain.store.db.mapper import saved_id
from domain.store.db.pipeline_mapper import Adapter, Factory
from domain.store.db.pipeline_repository import (
    DbPipelineEdgeRepository,
    DbPipelineRepository,
    DbPipelineRunRepository,
    DbPipelineStepRepository,
    DbPipelineStepRunRepository,
)
from domain.store.db.repository import transaction
from models.domain.pipeline import Pipeline, PipelineRun, PipelineStepRun, RunStatus
from models.store.db import PipelineTable


class PipelineStore:

    def __init__(self, engine: Engine):
        self._engine = engine
        self._pipelines = DbPipelineRepository(engine)
        self._steps = DbPipelineStepRepository(engine)
        self._edges = DbPipelineEdgeRepository(engine)
        self._runs = DbPipelineRunRepository(engine)
        self._step_runs = DbPipelineStepRunRepository(engine)

    def list_pipelines(self, project_name: str) -> list[Pipeline]:
        """With their steps, sorted by name."""
        rows = self._pipelines.list_for_project(project_name)
        ids = [saved_id(row) for row in rows]
        steps = self._steps.list_for_pipelines(ids)
        edges = self._edges.list_for_pipelines(ids)
        return [Adapter.to_pipeline(row, steps[row_id], edges[row_id]) for row, row_id in zip(rows, ids, strict=True)]

    def get_pipeline(self, pipeline_id: int) -> Pipeline | None:
        row = self._pipelines.get(pipeline_id)
        return self._with_steps(row) if row else None

    def save_pipeline(self, pipeline: Pipeline) -> Pipeline:
        """The pipeline and exactly its steps (in their order) and edges, all
        in one transaction: a failure leaves the saved pipeline as it was."""
        with transaction(self._engine):
            row = self._pipelines.save(Factory.to_pipeline_row(pipeline))
            pipeline_id = saved_id(row)
            step_rows = [Factory.to_pipeline_step_row(step, pipeline_id, position) for position, step in enumerate(pipeline.steps)]
            saved_steps = self._steps.replace(pipeline_id, step_rows)
            step_ids = {step_row.name: saved_id(step_row) for step_row in saved_steps}
            edge_rows = [Factory.to_pipeline_edge_row(edge, pipeline_id, step_ids) for edge in pipeline.edges]
            saved_edges = self._edges.replace(pipeline_id, edge_rows)
        return Adapter.to_pipeline(row, saved_steps, saved_edges)

    def delete_pipeline(self, pipeline_id: int) -> bool:
        """Its steps and runs go with it (DB cascade)."""
        return self._pipelines.delete(pipeline_id)

    def _with_steps(self, row: PipelineTable) -> Pipeline:
        return Adapter.to_pipeline(
            row, self._steps.list_for_pipeline(saved_id(row)),
            self._edges.list_for_pipeline(saved_id(row)),
        )

    def save_pipeline_run(self, run: PipelineRun) -> PipelineRun:
        """The run only (its steps are saved one by one with ``save_pipeline_step_run``)."""
        return Adapter.to_pipeline_run(self._runs.save(Factory.to_pipeline_run_row(run)))

    def get_pipeline_run(self, run_id: int) -> PipelineRun | None:
        """With its steps."""
        row = self._runs.get(run_id)
        return Adapter.to_pipeline_run(row, self._step_runs.list_for_run(saved_id(row))) if row else None

    def list_pipeline_runs(self, pipeline_id: int, limit: int = 20) -> list[PipelineRun]:
        """With their steps, newest first."""
        rows = self._runs.list_for_pipeline(pipeline_id, limit)
        step_runs = self._step_runs.list_for_runs([saved_id(row) for row in rows])
        return [Adapter.to_pipeline_run(row, step_runs[saved_id(row)]) for row in rows]

    def delete_pipeline_run(self, run_id: int) -> bool:
        """Its step runs go with it (DB cascade); the agent runs stay."""
        return self._runs.delete(run_id)

    def list_pipeline_runs_by_status(self, status: RunStatus) -> list[PipelineRun]:
        return [Adapter.to_pipeline_run(row) for row in self._runs.list_by_status(status.value)]

    def claim_next_pipeline_run(self) -> PipelineRun | None:
        """The oldest queued run, already switched to RUNNING (worker queue)."""
        row = self._runs.claim_next()
        return Adapter.to_pipeline_run(row) if row else None

    def save_pipeline_step_run(self, step_run: PipelineStepRun) -> PipelineStepRun:
        row = self._step_runs.save(Factory.to_pipeline_step_run_row(step_run))
        return Adapter.to_pipeline_step_run(row)
