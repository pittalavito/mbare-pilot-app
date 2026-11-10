"""The evaluations launched from the Metriche page (table evaluation_run), also the worker's queue."""
from sqlalchemy.engine import Engine
from sqlmodel import col, select, update

from domain.store.db.repository import SqlRepository
from models.store.db import EvaluationRunTable


class DbEvaluationRepository(SqlRepository[EvaluationRunTable]):

    def __init__(self, engine: Engine):
        super().__init__(engine, EvaluationRunTable)

    def list_recent(self, limit: int) -> list[EvaluationRunTable]:
        """Newest first."""
        statement = select(EvaluationRunTable).order_by(col(EvaluationRunTable.id).desc()).limit(limit)
        with self._session() as session:
            return list(session.exec(statement).all())

    def claim_next(self) -> EvaluationRunTable | None:
        """The oldest queued run, now running; None when there is none. The
        update only succeeds while it is still queued: two workers never take the same."""
        with self._session() as session:
            while True:
                row = session.exec(select(EvaluationRunTable).where(EvaluationRunTable.status == "queued")
                                   .order_by(col(EvaluationRunTable.id))).first()
                if row is None:
                    return None
                claimed = session.exec(update(EvaluationRunTable).where(col(EvaluationRunTable.id) == row.id,  # type: ignore[call-overload]
                                                                        col(EvaluationRunTable.status) == "queued").values(status="running"))
                session.commit()
                if claimed.rowcount == 1:
                    session.refresh(row)
                    return row
