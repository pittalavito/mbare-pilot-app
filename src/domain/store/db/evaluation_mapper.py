"""Evaluations: domain ``EvaluationRun`` <-> ``evaluation_run`` rows."""
from domain.store.db.mapper import as_utc
from models.domain.evaluation import EvaluationKind, EvaluationRun, EvaluationStatus
from models.store.db import EvaluationRunTable


class Adapter:
    """Read seam: DB rows -> domain models."""

    @staticmethod
    def to_evaluation_run(row: EvaluationRunTable) -> EvaluationRun:
        return EvaluationRun(id=row.id, kind=EvaluationKind(row.kind), models=list(row.models), embedders=list(row.embedders),
                             status=EvaluationStatus(row.status), report=row.report, error=row.error, created_at=as_utc(row.created_at),
                             finished_at=as_utc(row.finished_at) if row.finished_at else None)


class Factory:
    """Write seam: domain models -> DB rows."""

    @staticmethod
    def to_evaluation_row(run: EvaluationRun) -> EvaluationRunTable:
        return EvaluationRunTable(**{**run.model_dump(), "kind": run.kind.value, "status": run.status.value})
