"""Copilot's executions: the sessions (task, plan, status, repository), their
chat messages and the turns sent to the CLI with the AI credits they used.
The sessions double as the worker's queue (one running execution per
repository)."""
from datetime import datetime
from typing import Any

from sqlalchemy.engine import Engine

from core.error import NotFoundError
from domain.store.db.copilot_mapper import Adapter, Factory
from domain.store.db.copilot_repository import DbCopilotMessageRepository, DbCopilotSessionRepository, DbCopilotTurnRepository
from models.domain.copilot import CopilotMessage, CopilotModelUsage, CopilotSession, CopilotSessionStatus, CopilotTurnRecord


class CopilotStore:

    def __init__(self, engine: Engine):
        self._sessions = DbCopilotSessionRepository(engine)
        self._messages = DbCopilotMessageRepository(engine)
        self._turns = DbCopilotTurnRepository(engine)

    def save_session(self, session: CopilotSession) -> CopilotSession:
        """Insert (``id`` None) or update."""
        return Adapter.to_copilot_session(self._sessions.save(Factory.to_copilot_session_row(session)))

    def update_session(self, session_id: int, **changes: Any) -> CopilotSession:
        """Only ``changes`` (domain field names and values), not the whole row.
        NotFoundError when the session is gone (deleted meanwhile)."""
        session = self.get_session(session_id)
        if session is None:
            raise NotFoundError(f"Sessione Copilot non trovata: {session_id}")
        row = Factory.to_copilot_session_row(session.model_copy(update=changes))
        fields = {name: getattr(row, name) for name in changes}
        updated = self._sessions.update_fields(session_id, fields)
        if updated is None:
            raise NotFoundError(f"Sessione Copilot non trovata: {session_id}")
        return Adapter.to_copilot_session(updated)

    def get_session(self, session_id: int) -> CopilotSession | None:
        row = self._sessions.get(session_id)
        return Adapter.to_copilot_session(row) if row else None

    def list_sessions(self, project_name: str) -> list[CopilotSession]:
        """Newest first."""
        return [Adapter.to_copilot_session(row) for row in self._sessions.list_for_project(project_name)]

    def list_sessions_by_status(self, status: CopilotSessionStatus) -> list[CopilotSession]:
        return [Adapter.to_copilot_session(row) for row in self._sessions.list_by_status(status.value)]

    def claim_next_session(self) -> CopilotSession | None:
        """The next queued execution whose repository is free, now ``running``."""
        row = self._sessions.claim_next()
        return Adapter.to_copilot_session(row) if row else None

    def delete_session(self, session_id: int) -> bool:
        """With its messages."""
        return self._sessions.delete(session_id)

    def add_message(self, message: CopilotMessage) -> CopilotMessage:
        return Adapter.to_copilot_message(self._messages.save(Factory.to_copilot_message_row(message)))

    def list_messages(self, session_id: int) -> list[CopilotMessage]:
        """Oldest first."""
        return [Adapter.to_copilot_message(row) for row in self._messages.list_for_session(session_id)]

    def add_turn(self, turn: CopilotTurnRecord) -> CopilotTurnRecord:
        return Adapter.to_copilot_turn(self._turns.save(Factory.to_copilot_turn_row(turn)))

    def list_turns(self, limit: int = 100, project_name: str | None = None) -> list[CopilotTurnRecord]:
        """Newest first."""
        return [Adapter.to_copilot_turn(row) for row in self._turns.list_recent(limit, project_name)]

    def list_session_turns(self, session_id: int) -> list[CopilotTurnRecord]:
        """Oldest first."""
        return [Adapter.to_copilot_turn(row) for row in self._turns.list_for_session(session_id)]

    def usage_by_model(self, since: datetime | None = None, project_name: str | None = None) -> list[CopilotModelUsage]:
        """The most AI credits first."""
        return [Adapter.to_copilot_model_usage(row) for row in self._turns.totals_by_model(since, project_name)]
