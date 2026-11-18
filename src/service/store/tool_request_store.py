"""The requests of tools for Claude Code and the token of its MCP server (Postgres)."""
from datetime import datetime, timezone

from sqlalchemy.engine import Engine

from domain.store.db.mapper import as_utc
from domain.store.db.tool_request_repository import DbDevAccessRepository, DbToolRequestRepository
from models.domain.tool_request import ToolRequest
from models.store.db import DevAccessTable, ToolRequestTable


def _request(row: ToolRequestTable) -> ToolRequest:
    request = ToolRequest.model_validate(row.model_dump())
    request.created_at, request.updated_at = as_utc(request.created_at), as_utc(request.updated_at)
    return request


class ToolRequestStore:

    def __init__(self, engine: Engine):
        self._requests = DbToolRequestRepository(engine)
        self._access = DbDevAccessRepository(engine)

    def save(self, request: ToolRequest) -> ToolRequest:
        """New or updated (by ``id``)."""
        return _request(self._requests.save(ToolRequestTable(**request.model_dump(mode="json", exclude={"created_at", "updated_at"}),
                                                             created_at=request.created_at, updated_at=request.updated_at)))

    def get(self, request_id: int) -> ToolRequest | None:
        row = self._requests.get(request_id)
        return _request(row) if row else None

    def list_requests(self) -> list[ToolRequest]:
        """Newest first."""
        return [_request(row) for row in self._requests.newest_first()]

    def token_hash(self) -> str | None:
        row = self._access.get(1)
        return row.token_hash if row else None

    def save_token_hash(self, token_hash: str) -> None:
        self._access.save(DevAccessTable(id=1, token_hash=token_hash, created_at=datetime.now(timezone.utc)))
