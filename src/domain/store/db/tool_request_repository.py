"""The requests of tools (table tool_request) and the token of Claude Code's MCP server (table dev_access)."""
from sqlalchemy.engine import Engine
from sqlmodel import col, select

from domain.store.db.repository import SqlRepository
from models.store.db import DevAccessTable, ToolRequestTable


class DbToolRequestRepository(SqlRepository[ToolRequestTable]):

    def __init__(self, engine: Engine):
        super().__init__(engine, ToolRequestTable)

    def newest_first(self) -> list[ToolRequestTable]:
        with self._session() as session:
            return list(session.exec(select(ToolRequestTable).order_by(col(ToolRequestTable.id).desc())).all())


class DbDevAccessRepository(SqlRepository[DevAccessTable]):

    def __init__(self, engine: Engine):
        super().__init__(engine, DevAccessTable)
