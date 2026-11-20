"""Records stored in Redis (Pydantic, serialized as JSON)."""
from datetime import datetime

from pydantic import BaseModel, Field

from models.domain.agent import GenerationRecord, ModelTranscript, ToolCallRecord


class AgentTraceRecord(BaseModel):
    """Verbatim trace of one agent run (keyspace agent-trace, suffix = run_id)."""
    run_id: str
    input: str
    output: str
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    generations: list[GenerationRecord] = Field(default_factory=list)
    project_name: str | None = None
    transcript: ModelTranscript | None = None
    """The masked exchange with the model."""


class WorkerHeartbeatRecord(BaseModel):
    """Last heartbeat of a running worker (keyspace worker, suffix = worker_id, short TTL)."""
    worker_id: str
    host: str
    pid: int
    started_at: datetime
    last_seen: datetime
    busy_run_id: int | None = None
    busy_copilot_session_id: int | None = None


class MaskRecord(BaseModel):
    """One value of a project's masking map (keyspace mask)."""
    category: str
    value: str
    alias: str
    manual: bool = False
