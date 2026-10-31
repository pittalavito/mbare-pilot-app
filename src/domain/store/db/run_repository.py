"""Agent run facts (tables agent_run + tool_call). The verbatim traces live in Redis."""
from sqlalchemy.engine import Engine
from sqlmodel import col, delete, select

from domain.store.db.repository import SqlRepository
from models.store.db import AgentRunTable, ToolCallTable


class DbRunRepository(SqlRepository[AgentRunTable]):

    def __init__(self, engine: Engine):
        super().__init__(engine, AgentRunTable)

    def save_rows(self, run_row: AgentRunTable, tool_rows: list[ToolCallTable]) -> None:
        """Persist one run and its tool calls in one transaction. Saving an
        existing run_id replaces its tool calls."""
        with self._session() as session:
            session.exec(delete(ToolCallTable).where(col(ToolCallTable.run_id) == run_row.run_id))
            session.merge(run_row)
            session.flush()
            session.add_all(tool_rows)
            session.commit()

    def list_recent(self, limit: int = 100) -> list[AgentRunTable]:
        """Most recent runs first."""
        statement = select(AgentRunTable).order_by(col(AgentRunTable.created_at).desc()).limit(limit)
        with self._session() as session:
            return list(session.exec(statement).all())

    def list_recent_tool_calls(self, limit: int = 100) -> list[ToolCallTable]:
        """Most recent tool calls first; calls of the same run in call order."""
        statement = (
            select(ToolCallTable)
            .order_by(col(ToolCallTable.created_at).desc(), col(ToolCallTable.position))
            .limit(limit)
        )
        with self._session() as session:
            return list(session.exec(statement).all())
