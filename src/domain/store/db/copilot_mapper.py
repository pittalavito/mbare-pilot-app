"""Copilot: domain sessions, messages and turns <-> ``copilot_session`` /
``copilot_message`` / ``copilot_turn`` rows. A turn's usage is one nested
model in the domain and flat columns (``USAGE_COLUMNS``) in the DB."""
from domain.store.db.copilot_repository import USAGE_COLUMNS
from domain.store.db.mapper import as_utc
from models.domain.copilot import (
    CopilotMessage,
    CopilotMessageRole,
    CopilotModelUsage,
    CopilotPhase,
    CopilotSession,
    CopilotSessionStatus,
    CopilotTurnRecord,
    CopilotUsage,
)
from models.store.db import CopilotMessageTable, CopilotSessionTable, CopilotTurnTable


class Adapter:
    """Read seam: DB rows -> domain models."""

    @staticmethod
    def to_copilot_session(row: CopilotSessionTable) -> CopilotSession:
        return CopilotSession(**{
            **row.model_dump(),
            "status": CopilotSessionStatus(row.status),
            "created_at": as_utc(row.created_at),
            "updated_at": as_utc(row.updated_at),
            "started_at": as_utc(row.started_at) if row.started_at else None,
            "finished_at": as_utc(row.finished_at) if row.finished_at else None,
        })

    @staticmethod
    def to_copilot_turn(row: CopilotTurnTable) -> CopilotTurnRecord:
        data = row.model_dump()
        usage = CopilotUsage(**{name: data.pop(name) for name in USAGE_COLUMNS})
        return CopilotTurnRecord(**{**data, "phase": CopilotPhase(row.phase), "usage": usage, "created_at": as_utc(row.created_at)})

    @staticmethod
    def to_copilot_model_usage(row: tuple) -> CopilotModelUsage:
        """A row of ``totals_by_model``: ``(model, turns, *usage sums)``."""
        return CopilotModelUsage(model=row[0], turns=row[1], usage=CopilotUsage(**dict(zip(USAGE_COLUMNS, row[2:], strict=False))))

    @staticmethod
    def to_copilot_message(row: CopilotMessageTable) -> CopilotMessage:
        return CopilotMessage(**{**row.model_dump(), "role": CopilotMessageRole(row.role), "created_at": as_utc(row.created_at)})


class Factory:
    """Write seam: domain models -> DB rows."""

    @staticmethod
    def to_copilot_session_row(session: CopilotSession) -> CopilotSessionTable:
        return CopilotSessionTable(**{**session.model_dump(), "status": session.status.value, "changed_files": list(session.changed_files)})

    @staticmethod
    def to_copilot_turn_row(turn: CopilotTurnRecord) -> CopilotTurnTable:
        data = turn.model_dump(exclude={"usage"})
        return CopilotTurnTable(**{**data, **turn.usage.model_dump(), "phase": turn.phase.value})

    @staticmethod
    def to_copilot_message_row(message: CopilotMessage) -> CopilotMessageTable:
        return CopilotMessageTable(**{**message.model_dump(), "role": message.role.value})
