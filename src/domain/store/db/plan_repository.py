"""The plans of the activities (table activity_plan)."""
from sqlalchemy.engine import Engine
from sqlmodel import col, select

from domain.store.db.repository import SqlRepository
from models.store.db import ActivityPlanTable


class DbActivityPlanRepository(SqlRepository[ActivityPlanTable]):

    def __init__(self, engine: Engine):
        super().__init__(engine, ActivityPlanTable)

    def latest(self, project_name: str, activity: str) -> ActivityPlanTable | None:
        statement = (select(ActivityPlanTable)
                     .where(ActivityPlanTable.project_name == project_name, ActivityPlanTable.activity == activity)
                     .order_by(col(ActivityPlanTable.id).desc()))
        with self._session() as session:
            return session.exec(statement).first()

    def list_all(self) -> list[ActivityPlanTable]:
        """Newest first."""
        with self._session() as session:
            return list(session.exec(select(ActivityPlanTable).order_by(col(ActivityPlanTable.id).desc())).all())

    def list_for_project(self, project_name: str) -> list[ActivityPlanTable]:
        """Newest first."""
        statement = select(ActivityPlanTable).where(ActivityPlanTable.project_name == project_name).order_by(col(ActivityPlanTable.id).desc())
        with self._session() as session:
            return list(session.exec(statement).all())
