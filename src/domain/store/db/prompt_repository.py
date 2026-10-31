"""System prompt versions (table system_prompt). Versions are immutable: the
only write is ``create_version``."""
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.engine import Engine
from sqlmodel import col, select

from domain.store.db.repository import SqlRepository
from models.store.db import SystemPromptTable


class DbPromptRepository(SqlRepository[SystemPromptTable]):

    def __init__(self, engine: Engine):
        super().__init__(engine, SystemPromptTable)

    def create_version(self, role_name: str, text: str) -> SystemPromptTable:
        """Append version ``max + 1`` of the role's prompt (1 for the first)."""
        with self._session() as session:
            current = session.exec(
                select(func.max(SystemPromptTable.version)).where(SystemPromptTable.role_name == role_name)
            ).one()
            row = SystemPromptTable(
                role_name=role_name,
                version=(current or 0) + 1,
                text=text,
                created_at=datetime.now(timezone.utc),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def list_versions(self, role_name: str | None = None) -> list[SystemPromptTable]:
        """Versions of one role (or of every role), newest first."""
        statement = select(SystemPromptTable)
        if role_name is not None:
            statement = statement.where(SystemPromptTable.role_name == role_name)
        statement = statement.order_by(col(SystemPromptTable.role_name), col(SystemPromptTable.version).desc())
        with self._session() as session:
            return list(session.exec(statement).all())
