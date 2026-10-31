"""DB store facade: one import point for the DB persistence layer.

Re-exports the DB repositories and holds the two translation seams as
static-method classes: ``Adapter`` (rows -> domain models, reads) and
``Factory`` (domain models -> rows, writes).
"""
from datetime import datetime, timezone

from domain.store.db.atlassian_favorite_repository import DbAtlassianFavoriteRepository
from domain.store.db.atlassian_repository import DbAtlassianRepository
from domain.store.db.copilot_repository import USAGE_COLUMNS, DbCopilotMessageRepository, DbCopilotSessionRepository, DbCopilotTurnRepository
from domain.store.db.repository import Engine, transaction
from models.domain.atlassian import AtlassianFavorite, AtlassianSettings, FavoriteKind
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
from models.store.db import (
    AtlassianFavoriteTable,
    CopilotMessageTable,
    CopilotSessionTable,
    CopilotTurnTable,
    ProjectAtlassianTable,
)

__all__ = [
    "Engine",
    "transaction",
    "DbAtlassianFavoriteRepository",
    "DbAtlassianRepository",
    "DbCopilotMessageRepository",
    "DbCopilotSessionRepository",
    "DbCopilotTurnRepository",
    "Adapter",
    "Factory",
]


def _as_utc(value: datetime) -> datetime:
    """Backends without timezone support (e.g. SQLite) return naive datetimes: they are UTC."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class Adapter:
    """Read seam: DB rows -> domain models."""

    @staticmethod
    def to_copilot_session(row: CopilotSessionTable) -> CopilotSession:
        return CopilotSession(**{
            **row.model_dump(),
            "status": CopilotSessionStatus(row.status),
            "created_at": _as_utc(row.created_at),
            "updated_at": _as_utc(row.updated_at),
            "started_at": _as_utc(row.started_at) if row.started_at else None,
            "finished_at": _as_utc(row.finished_at) if row.finished_at else None,
        })

    @staticmethod
    def to_copilot_turn(row: CopilotTurnTable) -> CopilotTurnRecord:
        data = row.model_dump()
        usage = CopilotUsage(**{name: data.pop(name) for name in USAGE_COLUMNS})
        return CopilotTurnRecord(**{**data, "phase": CopilotPhase(row.phase), "usage": usage, "created_at": _as_utc(row.created_at)})

    @staticmethod
    def to_copilot_model_usage(row: tuple) -> CopilotModelUsage:
        """A row of ``totals_by_model``: ``(model, turns, *usage sums)``."""
        return CopilotModelUsage(model=row[0], turns=row[1], usage=CopilotUsage(**dict(zip(USAGE_COLUMNS, row[2:], strict=False))))

    @staticmethod
    def to_copilot_message(row: CopilotMessageTable) -> CopilotMessage:
        return CopilotMessage(**{**row.model_dump(), "role": CopilotMessageRole(row.role), "created_at": _as_utc(row.created_at)})



    @staticmethod
    def to_atlassian_settings(row: ProjectAtlassianTable, api_token: str) -> AtlassianSettings:
        """``api_token`` is the decrypted ``row.api_token``."""
        return AtlassianSettings.model_validate({**row.model_dump(), "api_token": api_token})

    @staticmethod
    def to_atlassian_favorite(row: AtlassianFavoriteTable) -> AtlassianFavorite:
        favorite = AtlassianFavorite.model_validate({**row.model_dump(), "kind": FavoriteKind(row.kind)})
        favorite.created_at = _as_utc(favorite.created_at)
        return favorite


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

    @staticmethod
    def to_atlassian_row(settings: AtlassianSettings, encrypted_token: str) -> ProjectAtlassianTable:
        return ProjectAtlassianTable(
            project_name=settings.project_name,
            base_url=settings.base_url,
            email=settings.email,
            api_token=encrypted_token,
            jira_project_key=settings.jira_project_key,
            confluence_space_key=settings.confluence_space_key,
        )

    @staticmethod
    def to_atlassian_favorite_row(favorite: AtlassianFavorite) -> AtlassianFavoriteTable:
        return AtlassianFavoriteTable(**{**favorite.model_dump(), "kind": favorite.kind.value})
