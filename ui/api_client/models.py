"""What the UI receives from the API (its own copy of the contract: the UI
never imports the backend's models)."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class Project(BaseModel):
    name: str
    description: str
    source: str
    """``folder`` | ``scratch``."""
    root_path: str
    embedding_model: str
    created_at: datetime
    folder_exists: bool


class FolderEntry(BaseModel):
    name: str
    path: str


class FolderListing(BaseModel):
    path: str
    parent: str | None
    subfolders: list[FolderEntry]


class Agent(BaseModel):
    name: str
    project_name: str | None
    description: str
    role_name: str
    prompt_id: int
    prompt_version: int | None
    model: str
    max_steps: int
    tool_names: list[str]
    blocked_reason: str | None
    """None = runnable."""


class Role(BaseModel):
    name: str
    project_name: str | None
    description: str
    active: bool


class Prompt(BaseModel):
    id: int
    role_name: str
    version: int
    text: str
    active: bool
    created_at: datetime


class PromptVersion(BaseModel):
    prompt: Prompt
    created: bool
    """False = identical to the latest version, nothing new."""


class Tool(BaseModel):
    name: str
    description: str
    available: bool


class ModelChoices(BaseModel):
    choices: list[str]
    usable: list[str]


# --------------------------------------------------------------------- chat

class Chatbot(BaseModel):
    id: int
    project_name: str
    name: str
    description: str
    system_prompt: str
    prompt_version: int
    model: str
    max_steps: int
    tool_names: list[str]


class Conversation(BaseModel):
    id: int
    chatbot_id: int
    title: str
    created_at: datetime
    updated_at: datetime


class Message(BaseModel):
    id: int
    conversation_id: int
    role: str
    """``user`` | ``assistant`` | ``error``."""
    content: str
    run_id: str | None
    created_at: datetime


# --------------------------------------------------------------------- data

class DataFile(BaseModel):
    name: str
    kind: str
    size: int
    modified_at: datetime


# ---------------------------------------------------------------------- git

class Repository(BaseModel):
    path: str
    name: str


class Commit(BaseModel):
    hash: str
    short_hash: str
    author: str
    email: str
    date: datetime
    subject: str


class Change(BaseModel):
    path: str
    kind: str
    staged: bool
    unstaged: bool
    original_path: str | None


class GitStatus(BaseModel):
    branch: str | None
    upstream: str | None
    ahead: int
    behind: int
    is_clean: bool
    changes: list[Change]


# --------------------------------------------------------------- automation

class StepAgent(BaseModel):
    system_prompt: str
    prompt_version: int = 1
    model: str
    max_steps: int = 4
    tool_names: list[str] = []


class Step(BaseModel):
    id: int | None = None
    name: str
    kind: str
    """``agent`` | ``agent_config`` | ``function``."""
    input_template: str
    agent: StepAgent | None = None
    agent_config_name: str | None = None
    function_name: str | None = None
    params: dict[str, Any] = {}


class Pipeline(BaseModel):
    id: int
    project_name: str
    name: str
    description: str
    active: bool
    steps: list[Step]


class StepRun(BaseModel):
    position: int
    name: str
    kind: str
    status: str
    input: str
    output: str | None
    error: str | None
    agent_run_id: str | None
    started_at: datetime | None
    finished_at: datetime | None


class PipelineRun(BaseModel):
    id: int
    pipeline_id: int
    status: str
    """``queued`` | ``running`` | ``done`` | ``failed``."""
    input: str
    output: str | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    steps: list[StepRun]

    @property
    def finished(self) -> bool:
        return self.status in ("done", "failed")


class Worker(BaseModel):
    worker_id: str
    host: str
    pid: int
    started_at: datetime
    last_seen: datetime
    busy_run_id: int | None
    """None = waiting for the queue."""


class FunctionParam(BaseModel):
    name: str
    type: str
    """``bool`` | ``int`` | ``float`` | ``str``."""
    default: Any = None
    description: str | None = None


class Function(BaseModel):
    name: str
    description: str
    params: list[FunctionParam]


# ---------------------------------------------------------------- atlassian

class AtlassianSettings(BaseModel):
    base_url: str
    email: str
    has_token: bool
    jira_project_key: str
    confluence_space_key: str


class AtlassianUser(BaseModel):
    display_name: str
    email: str | None


# -------------------------------------------------------------------- admin

class AppConfig(BaseModel):
    settings: dict[str, Any]
    redis_dashboard_port: int
    postgres_dashboard_port: int


class Tokens(BaseModel):
    input_tokens: int
    output_tokens: int
    cost_eur: float


class RunSummary(BaseModel):
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
    agent_tokens: Tokens
    tool_tokens: Tokens
    total_tokens: Tokens
    tool_names: list[str]
    created_at: datetime


class ToolCall(BaseModel):
    run_id: str
    tool_name: str
    ok: bool
    error: str | None
    latency_ms: float
    tokens: Tokens
    created_at: datetime


class CatalogModel(BaseModel):
    provider: str
    model: str
    input_per_1m: float = 0.0
    output_per_1m: float = 0.0
    active: bool = True
    in_use: bool = False
