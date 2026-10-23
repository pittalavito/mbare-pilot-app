"""Response/request models of the Admin API: app config (secrets masked),
observability facts, the model catalog and the DB backups."""
from datetime import datetime

from pydantic import BaseModel

from models.domain.agent import AgentRunSummary, ToolCallSummary
from models.domain.backup import BackupFile
from models.domain.chat import ChatModel


class ConfigResponse(BaseModel):
    settings: dict[str, object]
    """Every setting, secrets masked."""
    redis_dashboard_port: int
    postgres_dashboard_port: int


class TokensResponse(BaseModel):
    input_tokens: int
    output_tokens: int
    cost_eur: float


class RunSummaryResponse(BaseModel):
    run_id: str
    project_name: str | None
    origin: str
    config_name: str
    role_name: str
    prompt_version: int
    model: str
    ok: bool
    error: str | None
    latency_ms: float
    agent_tokens: TokensResponse
    tool_tokens: TokensResponse
    total_tokens: TokensResponse
    tool_names: list[str]
    created_at: datetime

    @classmethod
    def from_summary(cls, summary: AgentRunSummary) -> "RunSummaryResponse":
        return cls(**summary.model_dump())


class ToolCallResponse(BaseModel):
    run_id: str
    tool_name: str
    ok: bool
    error: str | None
    latency_ms: float
    tokens: TokensResponse
    created_at: datetime

    @classmethod
    def from_summary(cls, summary: ToolCallSummary) -> "ToolCallResponse":
        return cls(**summary.model_dump())


class CatalogModelBody(BaseModel):
    """One model of the catalog, both ways; ``in_use`` is ignored on save."""
    provider: str
    model: str
    input_per_1m: float = 0.0
    output_per_1m: float = 0.0
    active: bool = True
    in_use: bool = False
    """Used by an agent, chatbot or automation step: deactivate it, do not delete it."""

    @classmethod
    def from_model(cls, model: ChatModel, in_use: bool) -> "CatalogModelBody":
        return cls(**model.model_dump(), in_use=in_use)

    def to_model(self) -> ChatModel:
        return ChatModel.model_validate(self.model_dump(exclude={"in_use"}))


class BackupResponse(BaseModel):
    name: str
    size: int
    created_at: datetime

    @classmethod
    def from_backup(cls, backup: BackupFile) -> "BackupResponse":
        return cls(**backup.model_dump())


class BackupsResponse(BaseModel):
    folder: str
    """Where the exports are written."""
    backups: list[BackupResponse]
    """Newest first."""
