"""Pipelines, their steps and runs (tables pipeline, pipeline_step,
pipeline_run, pipeline_step_run). ``pipeline_run`` is also the worker queue."""
from datetime import datetime, timezone

from sqlalchemy.engine import Engine
from sqlmodel import col, select

from domain.store.db.repository import SqlRepository
from models.store.db import PipelineRunTable, PipelineStepRunTable, PipelineStepTable, PipelineTable


class DbPipelineRepository(SqlRepository[PipelineTable]):

    def __init__(self, engine: Engine):
        super().__init__(engine, PipelineTable)

    def list_for_project(self, project_name: str) -> list[PipelineTable]:
        """A project's pipelines, sorted by name."""
        statement = select(PipelineTable).where(PipelineTable.project_name == project_name).order_by(PipelineTable.name)
        with self._session() as session:
            return list(session.exec(statement).all())


class DbPipelineStepRepository(SqlRepository[PipelineStepTable]):

    def __init__(self, engine: Engine):
        super().__init__(engine, PipelineStepTable)

    def list_for_pipeline(self, pipeline_id: int) -> list[PipelineStepTable]:
        """In execution order."""
        statement = select(PipelineStepTable).where(PipelineStepTable.pipeline_id == pipeline_id).order_by(PipelineStepTable.position)
        with self._session() as session:
            return list(session.exec(statement).all())

    def replace(self, pipeline_id: int, rows: list[PipelineStepTable]) -> list[PipelineStepTable]:
        """Make ``rows`` the pipeline's steps, in one transaction: rows with an
        id are updated, the others inserted, the steps missing from ``rows`` deleted."""
        keep = {row.id for row in rows if row.id is not None}
        with self._session() as session:
            for existing in session.exec(select(PipelineStepTable).where(PipelineStepTable.pipeline_id == pipeline_id)):
                if existing.id not in keep:
                    session.delete(existing)
            saved = [session.merge(row) for row in rows]
            session.commit()
            for row in saved:
                session.refresh(row)
            return sorted(saved, key=lambda row: row.position)


class DbPipelineRunRepository(SqlRepository[PipelineRunTable]):

    def __init__(self, engine: Engine):
        super().__init__(engine, PipelineRunTable)

    def list_for_pipeline(self, pipeline_id: int, limit: int) -> list[PipelineRunTable]:
        """Newest first."""
        statement = (
            select(PipelineRunTable).where(PipelineRunTable.pipeline_id == pipeline_id)
            .order_by(col(PipelineRunTable.id).desc()).limit(limit)
        )
        with self._session() as session:
            return list(session.exec(statement).all())

    def claim_next(self) -> PipelineRunTable | None:
        """The oldest ``queued`` run, switched to ``running`` atomically: with
        ``FOR UPDATE SKIP LOCKED`` two workers never take the same run."""
        statement = (
            select(PipelineRunTable).where(PipelineRunTable.status == "queued")
            .order_by(PipelineRunTable.id).limit(1).with_for_update(skip_locked=True)
        )
        with self._session() as session:
            row = session.exec(statement).first()
            if row is None:
                return None
            row.status = "running"
            row.started_at = datetime.now(timezone.utc)
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def list_by_status(self, status: str) -> list[PipelineRunTable]:
        with self._session() as session:
            return list(session.exec(select(PipelineRunTable).where(PipelineRunTable.status == status)).all())


class DbPipelineStepRunRepository(SqlRepository[PipelineStepRunTable]):

    def __init__(self, engine: Engine):
        super().__init__(engine, PipelineStepRunTable)

    def list_for_run(self, pipeline_run_id: int) -> list[PipelineStepRunTable]:
        """In execution order."""
        statement = (
            select(PipelineStepRunTable).where(PipelineStepRunTable.pipeline_run_id == pipeline_run_id)
            .order_by(PipelineStepRunTable.position)
        )
        with self._session() as session:
            return list(session.exec(statement).all())
