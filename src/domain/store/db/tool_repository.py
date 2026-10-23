"""Tool catalog (table tool)."""
from sqlalchemy.engine import Engine
from sqlmodel import select

from domain.store.db.repository import SqlRepository
from models.store.db import ToolTable


class DbToolRepository(SqlRepository[ToolTable]):

    def __init__(self, engine: Engine):
        super().__init__(engine, ToolTable)

    def list_sorted(self) -> list[ToolTable]:
        with self._session() as session:
            return list(session.exec(select(ToolTable).order_by(ToolTable.name)).all())
