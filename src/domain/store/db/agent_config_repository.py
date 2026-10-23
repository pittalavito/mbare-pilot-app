"""Agent configurations (table agent_config)."""
from sqlalchemy import or_
from sqlalchemy.engine import Engine
from sqlmodel import select

from domain.store.db.repository import SqlRepository
from models.store.db import AgentConfigTable


class DbAgentConfigRepository(SqlRepository[AgentConfigTable]):

    def __init__(self, engine: Engine):
        super().__init__(engine, AgentConfigTable)

    def list_scoped(self, project_name: str | None, include_global: bool) -> list[AgentConfigTable]:
        """Global rows only (``project_name`` None), or one project's rows,
        optionally together with the global ones. Sorted by name."""
        statement = select(AgentConfigTable)
        if project_name is None:
            statement = statement.where(AgentConfigTable.project_name.is_(None))
        elif include_global:
            statement = statement.where(or_(AgentConfigTable.project_name.is_(None), AgentConfigTable.project_name == project_name))
        else:
            statement = statement.where(AgentConfigTable.project_name == project_name)
        with self._session() as session:
            return list(session.exec(statement.order_by(AgentConfigTable.name)).all())
