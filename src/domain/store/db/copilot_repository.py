"""Copilot sessions, their messages and the usage of their turns (tables copilot_session,
copilot_message, copilot_turn). ``copilot_session`` is also the worker queue of the executions
(``status``) and of the planning turns (``planning_turn``)."""
from datetime import datetime, timezone

from sqlalchemy import func, text, update
from sqlalchemy.engine import Engine
from sqlmodel import col, select

from domain.store.db.repository import SqlRepository
from models.store.db import CopilotMessageTable, CopilotSessionTable, CopilotTurnTable

# todof: forse possiamo far meglio?
USAGE_COLUMNS = [
    "premium_requests", "nano_aiu", "input_tokens", "output_tokens",
    "cache_read_tokens", "cache_write_tokens", "reasoning_tokens", "api_duration_ms",
]
"""The usage columns of ``copilot_turn`` (the fields of the domain's CopilotUsage)."""


_CLAIM_LOCK = 7_031_001
"""Key of the advisory lock that serializes the claims of Copilot executions."""


def _repos(row: CopilotSessionTable) -> list[str]:
    """The repositories a session works on (``repository`` for the sessions made before ``repositories``)."""
    return row.repositories or [row.repository]


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

    def list_by_planning_turn(self, planning_turn: str) -> list[CopilotSessionTable]:
        with self._session() as session:
            return list(session.exec(select(CopilotSessionTable).where(CopilotSessionTable.planning_turn == planning_turn)).all())

    def update_fields(self, session_id: int, fields: dict) -> CopilotSessionTable | None:
        """``UPDATE ... SET <only these fields>``: the API and the worker write
        different fields of the same session at the same time (e.g. a cancel
        while the execution starts) and neither overwrites the other's."""
        with self._session() as session:
            session.exec(update(CopilotSessionTable).where(col(CopilotSessionTable.id) == session_id).values(**fields))
            session.commit()
            return session.get(CopilotSessionTable, session_id)

    def claim_next(self, worker_id: str | None = None) -> CopilotSessionTable | None:
        """The oldest ``queued`` session none of whose repositories (``repositories``,
        or ``repository`` for the sessions made before) has an execution running,
        switched to ``running`` atomically: ``FOR UPDATE SKIP LOCKED`` on the queue
        and, on Postgres, a transaction-level advisory lock, so two claims never
        both pick sessions sharing a repository."""
        with self._session() as session:
            if session.get_bind().dialect.name == "postgresql":
                session.exec(text("SELECT pg_advisory_xact_lock(:key)").bindparams(key=_CLAIM_LOCK))  # type: ignore[call-overload]  # a plain SQL statement
            running = session.exec(select(CopilotSessionTable).where(CopilotSessionTable.status == "running")).all()
            busy = {(row.project_name, repo) for row in running for repo in _repos(row)}
            queued = session.exec(
                select(CopilotSessionTable).where(CopilotSessionTable.status == "queued")
                .order_by(col(CopilotSessionTable.id)).with_for_update(skip_locked=True)
            ).all()
            row = next((row for row in queued if not any((row.project_name, repo) in busy for repo in _repos(row))), None)
            if row is None:
                session.commit()  # releases the advisory lock
                return None
            row.status = "running"
            row.claimed_by = worker_id
            row.started_at = row.updated_at = datetime.now(timezone.utc)
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def claim_next_planning_turn(self, worker_id: str | None = None) -> CopilotSessionTable | None:
        """The session whose planning turn has waited longest, switched from
        ``queued`` to ``running`` atomically (``FOR UPDATE SKIP LOCKED``). The
        repository being busy does not matter: plan mode only reads."""
        statement = (
            select(CopilotSessionTable).where(CopilotSessionTable.planning_turn == "queued")
            .order_by(col(CopilotSessionTable.updated_at), col(CopilotSessionTable.id)).limit(1).with_for_update(skip_locked=True)
        )
        with self._session() as session:
            row = session.exec(statement).first()
            if row is None:
                return None
            row.planning_turn = "running"
            row.claimed_by = worker_id
            row.updated_at = datetime.now(timezone.utc)
            session.add(row)
            session.commit()
            session.refresh(row)
            return row


class DbCopilotMessageRepository(SqlRepository[CopilotMessageTable]):

    def __init__(self, engine: Engine):
        super().__init__(engine, CopilotMessageTable)

    def list_for_session(self, session_id: int) -> list[CopilotMessageTable]:
        """Oldest first."""
        statement = select(CopilotMessageTable).where(col(CopilotMessageTable.session_id) == session_id).order_by(col(CopilotMessageTable.id))
        with self._session() as session:
            return list(session.exec(statement).all())


class DbCopilotTurnRepository(SqlRepository[CopilotTurnTable]):
    """What each turn used: the rows of the Observability → Copilot tab."""

    def __init__(self, engine: Engine):
        super().__init__(engine, CopilotTurnTable)

    def list_recent(self, limit: int, project_name: str | None = None) -> list[CopilotTurnTable]:
        """Newest first."""
        statement = select(CopilotTurnTable).order_by(col(CopilotTurnTable.id).desc()).limit(limit)
        if project_name is not None:
            statement = statement.where(CopilotTurnTable.project_name == project_name)
        with self._session() as session:
            return list(session.exec(statement).all())

    def list_for_session(self, session_id: int) -> list[CopilotTurnTable]:
        """Oldest first."""
        statement = select(CopilotTurnTable).where(col(CopilotTurnTable.session_id) == session_id).order_by(col(CopilotTurnTable.id))
        with self._session() as session:
            return list(session.exec(statement).all())

    def totals_by_model(self, since: datetime | None = None, project_name: str | None = None) -> list[tuple]:
        """``(model, turns, *usage sums)`` per model, the most AI credits first."""
        sums = [func.coalesce(func.sum(getattr(CopilotTurnTable, name)), 0) for name in USAGE_COLUMNS]
        statement = select(CopilotTurnTable.model, func.count(), *sums).group_by(CopilotTurnTable.model)
        if since is not None:
            statement = statement.where(CopilotTurnTable.created_at >= since)
        if project_name is not None:
            statement = statement.where(CopilotTurnTable.project_name == project_name)
        with self._session() as session:
            rows = [tuple(row) for row in session.exec(statement).all()]
        return sorted(rows, key=lambda row: row[2 + USAGE_COLUMNS.index("nano_aiu")], reverse=True)
