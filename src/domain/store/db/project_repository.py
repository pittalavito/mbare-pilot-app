"""Projects (table project)."""
from sqlalchemy.engine import Engine
from sqlmodel import col, select

from domain.store.db.repository import SqlRepository
from models.store.db import ProjectTable


class DbProjectRepository(SqlRepository[ProjectTable]):

    def __init__(self, engine: Engine):
        super().__init__(engine, ProjectTable)

    def list_recent(self, source: str | None = None) -> list[ProjectTable]:
        """Projects (optionally of one source), most recent first."""
        statement = select(ProjectTable)
        if source is not None:
            statement = statement.where(ProjectTable.source == source)
        statement = statement.order_by(col(ProjectTable.created_at).desc())
        with self._session() as session:
            return list(session.exec(statement).all())
