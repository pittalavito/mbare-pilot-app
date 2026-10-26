"""Copilot sessions and their messages (tables copilot_session,
copilot_message). ``copilot_session`` is also the worker queue of the executions."""
from datetime import datetime, timezone

from sqlalchemy.engine import Engine
from sqlalchemy import update
from sqlmodel import and_, col, exists, select

from domain.store.db.repository import SqlRepository
from models.store.db import CopilotMessageTable, CopilotSessionTable


class DbCopilotSessionRepository(SqlRepository[CopilotSessionTable]):

    def __init__(self, engine: Engine):
        super().__init__(engine, CopilotSessionTable)

    def list_for_project(self, project_name: str) -> list[CopilotSessionTable]:
        """Newest first."""
        statement = (
            select(CopilotSessionTable).where(CopilotSessionTable.project_name == project_name)
            .order_by(col(CopilotSessionTable.id).desc())
        )
        with self._session() as session:
            return list(session.exec(statement).all())

    def list_by_status(self, status: str) -> list[CopilotSessionTable]:
        with self._session() as session:
            return list(session.exec(select(CopilotSessionTable).where(CopilotSessionTable.status == status)).all())

    def update_fields(self, session_id: int, fields: dict) -> CopilotSessionTable | None:
        """``UPDATE ... SET <only these fields>``: the API and the worker write
        different fields of the same session at the same time (e.g. a cancel
        while the execution starts) and neither overwrites the other's."""
        with self._session() as session:
            session.exec(update(CopilotSessionTable).where(CopilotSessionTable.id == session_id).values(**fields))
            session.commit()
            return session.get(CopilotSessionTable, session_id)

    def claim_next(self) -> CopilotSessionTable | None:
        """The oldest ``queued`` session whose repository has no execution
        running, switched to ``running`` atomically (``FOR UPDATE SKIP LOCKED``)."""
        running = CopilotSessionTable.__table__.alias("running")
        busy = exists().where(and_(
            running.c.status == "running",
            running.c.project_name == CopilotSessionTable.project_name,
            running.c.repository == CopilotSessionTable.repository,
        ))
        statement = (
            select(CopilotSessionTable).where(CopilotSessionTable.status == "queued", ~busy)
            .order_by(CopilotSessionTable.id).limit(1).with_for_update(skip_locked=True)
        )
        with self._session() as session:
            row = session.exec(statement).first()
            if row is None:
                return None
            row.status = "running"
            row.started_at = row.updated_at = datetime.now(timezone.utc)
            session.add(row)
            session.commit()
            session.refresh(row)
            return row


class DbCopilotMessageRepository(SqlRepository[CopilotMessageTable]):

    def __init__(self, engine: Engine):
        super().__init__(engine, CopilotMessageTable)

    def list_for_session(self, session_id: int) -> list[CopilotMessageTable]:
        """Oldest first."""
        statement = select(CopilotMessageTable).where(CopilotMessageTable.session_id == session_id).order_by(CopilotMessageTable.id)
        with self._session() as session:
            return list(session.exec(statement).all())
