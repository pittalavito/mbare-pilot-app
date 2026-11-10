"""The «Elabora WIP» runs of each project (table wip_run)."""
from sqlalchemy.engine import Engine
from sqlmodel import col, select

from domain.store.db.repository import SqlRepository
from models.store.db import WipRunTable


class DbWipRunRepository(SqlRepository[WipRunTable]):

    def __init__(self, engine: Engine):
        super().__init__(engine, WipRunTable)

    def find(self, run_id: str) -> WipRunTable | None:
        with self._session() as session:
            return session.exec(select(WipRunTable).where(WipRunTable.run_id == run_id)).first()

    def list_for_project(self, project_name: str) -> list[WipRunTable]:
        """Newest first."""
        statement = select(WipRunTable).where(WipRunTable.project_name == project_name).order_by(col(WipRunTable.id).desc())
        with self._session() as session:
            return list(session.exec(statement).all())
