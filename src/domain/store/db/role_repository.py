"""Agent roles (table agent_role)."""
from sqlalchemy import or_
from sqlalchemy.engine import Engine
from sqlmodel import col, select

from domain.store.db.repository import SqlRepository
from models.store.db import AgentRoleTable


class DbRoleRepository(SqlRepository[AgentRoleTable]):

    def __init__(self, engine: Engine):
        super().__init__(engine, AgentRoleTable)

    def list_scoped(self, project_name: str | None, include_global: bool) -> list[AgentRoleTable]:
        """Global rows only (``project_name`` None), or one project's rows,
        optionally together with the global ones. Sorted by name."""
        statement = select(AgentRoleTable)
        if project_name is None:
            statement = statement.where(col(AgentRoleTable.project_name).is_(None))
        elif include_global:
            statement = statement.where(or_(col(AgentRoleTable.project_name).is_(None), col(AgentRoleTable.project_name) == project_name))
        else:
            statement = statement.where(AgentRoleTable.project_name == project_name)
        with self._session() as session:
            return list(session.exec(statement.order_by(AgentRoleTable.name)).all())
