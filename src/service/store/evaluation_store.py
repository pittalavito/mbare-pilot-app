"""The evaluations launched from the Metriche page (Postgres): also the worker's queue."""
from sqlalchemy.engine import Engine

from domain.store.db.evaluation_mapper import Adapter, Factory
from domain.store.db.evaluation_repository import DbEvaluationRepository
from models.domain.evaluation import EvaluationRun


class EvaluationStore:

    def __init__(self, engine: Engine):
        self._runs = DbEvaluationRepository(engine)

    def save_run(self, run: EvaluationRun) -> EvaluationRun:
        """New or updated (by ``id``)."""
        return Adapter.to_evaluation_run(self._runs.save(Factory.to_evaluation_row(run)))

    def list_runs(self, limit: int = 20) -> list[EvaluationRun]:
        """Newest first."""
        return [Adapter.to_evaluation_run(row) for row in self._runs.list_recent(limit)]

    def claim_next(self) -> EvaluationRun | None:
        """The oldest queued evaluation, now running; None when there is none."""
        row = self._runs.claim_next()
        return Adapter.to_evaluation_run(row) if row else None
