"""SQL tables (SQLModel). Rows never leave the store layer: domain/store/db/store.py
maps them to and from domain models.

Schema overview (project-centric):
  project ─┬─ project_atlassian, atlassian_favorite         (Jira + Confluence site, favorites)
           ├─ agent_role / system_prompt / agent_config   (project_name NULL = global)
           ├─ chatbot (with its own agent) ── conversation ── message
           │      └── automation_cache (cache: message → automation, from a message)
           ├─ pipeline ── pipeline_step, pipeline_edge (graph)
           │      └── pipeline_run (also the worker queue) ── pipeline_step_run
           ├─ document ── chunk (pgvector embedding)
           ├─ copilot_session (also the worker queue) ── copilot_message
           ├─ copilot_turn                                  (usage per turn, no FK: kept after deletion)
           └─ agent_run ── tool_call                        (+ verbatim trace in Redis)
  tool, function, chat_model: global catalogs.
"""
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, BigInteger, Column, DateTime, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


def _timestamp(**kwargs) -> datetime:
    return Field(sa_type=DateTime(timezone=True), **kwargs)


def _project_fk(nullable: bool) -> str | None:
    """FK to project.name; deleting a project deletes everything it owns."""
    return Field(default=None if nullable else ..., foreign_key="project.name", index=True, ondelete="CASCADE")


# ------------------------------------------------------------------ project

class ProjectTable(SQLModel, table=True):
    """Projects: a named folder on disk."""
    __tablename__ = "project"

    name: str = Field(primary_key=True)
    description: str = ""
    source: str = Field(index=True)
    root_path: str = Field(unique=True)
    embedding_model: str
    """Embedding model of the project's RAG index (EmbeddingModelName value)."""
    created_at: datetime = _timestamp()
    visible_note_types: list[str] | None = Field(default=None, sa_type=JSON)
    """The note types the Dati tab shows (NoteType values); NULL = the default ones."""


class ProjectAtlassianTable(SQLModel, table=True):
    """A project's Atlassian Cloud site (Jira + Confluence), one per project."""
    __tablename__ = "project_atlassian"

    project_name: str = Field(primary_key=True, foreign_key="project.name", ondelete="CASCADE")
    base_url: str
    email: str
    api_token: str
    """Encrypted with MBARE_PILOT_SECRET_KEY (core/secret_box.py)."""
    jira_project_key: str = ""
    confluence_space_key: str = ""


class AtlassianFavoriteTable(SQLModel, table=True):
    """A project's favorite Jira issues and Confluence pages."""
    __tablename__ = "atlassian_favorite"
    __table_args__ = (UniqueConstraint("project_name", "kind", "ref"),)

    id: int | None = Field(default=None, primary_key=True)
    project_name: str = _project_fk(nullable=False)
    kind: str
    """FavoriteKind value: jira_issue | confluence_page."""
    ref: str
    """Issue key or page id."""
    site: str
    """Base URL of the Atlassian site the favorite belongs to."""
    title: str
    url: str
    created_at: datetime = _timestamp()


# ------------------------------------------------------------------- agents

class AgentRoleTable(SQLModel, table=True):
    """Agent roles (e.g. ``hello``). ``project_name`` NULL = global."""
    __tablename__ = "agent_role"

    name: str = Field(primary_key=True)
    project_name: str | None = _project_fk(nullable=True)
    description: str = ""
    active: bool = True


class SystemPromptTable(SQLModel, table=True):
    """Immutable system prompt versions, numbered per role (scope = the role's)."""
    __tablename__ = "system_prompt"
    __table_args__ = (UniqueConstraint("role_name", "version"),)

    id: int | None = Field(default=None, primary_key=True)
    role_name: str = Field(foreign_key="agent_role.name", index=True, ondelete="CASCADE")
    version: int
    text: str = Field(sa_type=Text)
    active: bool = True
    created_at: datetime = _timestamp()


class AgentConfigTable(SQLModel, table=True):
    """Runnable agent configurations. ``project_name`` NULL = global."""
    __tablename__ = "agent_config"

    name: str = Field(primary_key=True)
    project_name: str | None = _project_fk(nullable=True)
    description: str = ""
    role_name: str = Field(foreign_key="agent_role.name", index=True, ondelete="CASCADE")
    prompt_id: int = Field(foreign_key="system_prompt.id", ondelete="CASCADE")
    model: str
    max_steps: int
    tool_names: list[str] = Field(default_factory=list, sa_type=JSON)
    """Names of the catalog tools the agent can call, in order."""


class ToolTable(SQLModel, table=True):
    """Tool catalog (agent-callable), synced from code at startup."""
    __tablename__ = "tool"

    name: str = Field(primary_key=True)
    description: str = ""


class FunctionTable(SQLModel, table=True):
    """Function catalog (Python pipeline steps), synced from code at startup."""
    __tablename__ = "function"

    name: str = Field(primary_key=True)
    description: str = ""


# --------------------------------------------------------------------- chat

class ChatbotTable(SQLModel, table=True):
    """A project's chatbot with its own agent (prompt, model, tools), separate
    from the agent configurations."""
    __tablename__ = "chatbot"
    __table_args__ = (UniqueConstraint("project_name", "name"),)

    id: int | None = Field(default=None, primary_key=True)
    project_name: str = _project_fk(nullable=False)
    name: str
    kind: str = "custom"
    """``automation`` (fixed tools, automation cache) | ``custom``."""
    description: str = ""
    system_prompt: str = Field(sa_type=Text)
    prompt_version: int = 1
    """Incremented whenever the system prompt changes (recorded on every run)."""
    model: str
    max_steps: int
    tool_names: list[str] = Field(default_factory=list, sa_type=JSON)
    rag_enabled: bool = False
    """NOTE: RAG behaviour of chatbots still to be defined (see README)."""
    created_at: datetime = _timestamp()
    updated_at: datetime = _timestamp()


class ConversationTable(SQLModel, table=True):
    __tablename__ = "conversation"

    id: int | None = Field(default=None, primary_key=True)
    chatbot_id: int = Field(foreign_key="chatbot.id", index=True, ondelete="CASCADE")
    title: str = ""
    created_at: datetime = _timestamp()
    updated_at: datetime = _timestamp(index=True)


class AutomationCacheTable(SQLModel, table=True):
    """A chatbot's cache entry: a message that launches an automation without
    the agent. The embedding is JSON, compared in Python: a chatbot has few."""
    __tablename__ = "automation_cache"

    id: int | None = Field(default=None, primary_key=True)
    chatbot_id: int = Field(foreign_key="chatbot.id", index=True, ondelete="CASCADE")
    message_id: int | None = Field(default=None, foreign_key="message.id", ondelete="SET NULL")
    """The user message it was made from: deleting the conversation keeps the entry."""
    text: str = Field(sa_type=Text)
    embedder: str
    embedding: list[float] = Field(default_factory=list, sa_type=JSON)
    pipeline_id: int = Field(foreign_key="pipeline.id", ondelete="CASCADE")
    pipeline_input: str = Field(default="", sa_type=Text)
    hits: int = 0
    created_at: datetime = _timestamp()


class MessageTable(SQLModel, table=True):
    __tablename__ = "message"

    id: int | None = Field(default=None, primary_key=True)
    conversation_id: int = Field(foreign_key="conversation.id", index=True, ondelete="CASCADE")
    role: str
    """``user`` | ``assistant``."""
    content: str = Field(sa_type=Text)
    run_id: str | None = Field(default=None, foreign_key="agent_run.run_id", ondelete="SET NULL")
    """The agent run that produced an assistant message."""
    created_at: datetime = _timestamp()


# ---------------------------------------------------------------- pipelines

class PipelineTable(SQLModel, table=True):
    """An automation: a graph of steps (pipeline_step) and edges (pipeline_edge)."""
    __tablename__ = "pipeline"
    __table_args__ = (UniqueConstraint("project_name", "name"),)

    id: int | None = Field(default=None, primary_key=True)
    project_name: str = _project_fk(nullable=False)
    name: str
    description: str = ""
    active: bool = True
    created_at: datetime = _timestamp()
    updated_at: datetime = _timestamp()


class PipelineStepTable(SQLModel, table=True):
    """One step of a pipeline. ``kind`` says which fields are used:
    ``agent`` (its own agent: system_prompt…tool_names), ``agent_config`` (a
    Library agent) or ``function`` (a function implemented in code)."""
    __tablename__ = "pipeline_step"

    id: int | None = Field(default=None, primary_key=True)
    pipeline_id: int = Field(foreign_key="pipeline.id", index=True, ondelete="CASCADE")
    position: int
    name: str
    kind: str
    input_template: str = Field(default="{input}", sa_type=Text)
    system_prompt: str | None = Field(default=None, sa_type=Text)
    prompt_version: int = 1
    model: str | None = None
    max_steps: int | None = None
    tool_names: list[str] = Field(default_factory=list, sa_type=JSON)
    agent_config_name: str | None = None
    """Plain column, no FK: a deleted Library agent makes the step fail with a clear error."""
    function_name: str | None = None
    params: dict = Field(default_factory=dict, sa_type=JSON)
    position_x: float = 0.0
    position_y: float = 0.0
    """Where the node is drawn in the graph editor."""


class PipelineEdgeTable(SQLModel, table=True):
    """An edge of a pipeline's graph: the output of ``source_step_id`` (NULL =
    the run input) feeds ``target_step_id`` when ``condition`` holds."""
    __tablename__ = "pipeline_edge"

    id: int | None = Field(default=None, primary_key=True)
    pipeline_id: int = Field(foreign_key="pipeline.id", index=True, ondelete="CASCADE")
    source_step_id: int | None = Field(default=None, foreign_key="pipeline_step.id", ondelete="CASCADE")
    target_step_id: int = Field(foreign_key="pipeline_step.id", ondelete="CASCADE")
    condition: str = "always"
    """EdgeConditionKind value."""
    value: str = ""


class PipelineRunTable(SQLModel, table=True):
    """One execution of a pipeline. Also the worker queue: the worker claims
    ``queued`` rows with ``SELECT ... FOR UPDATE SKIP LOCKED``."""
    __tablename__ = "pipeline_run"

    id: int | None = Field(default=None, primary_key=True)
    pipeline_id: int = Field(foreign_key="pipeline.id", index=True, ondelete="CASCADE")
    status: str = Field(index=True)
    """``queued`` | ``running`` | ``done`` | ``failed``."""
    input: str = Field(default="", sa_type=Text)
    output: str | None = Field(default=None, sa_type=Text)
    error: str | None = Field(default=None, sa_type=Text)
    created_at: datetime = _timestamp(index=True)
    started_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    finished_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


class PipelineStepRunTable(SQLModel, table=True):
    """One step of a run. Name and kind are copied from the step, so the
    history stays readable after the pipeline is edited."""
    __tablename__ = "pipeline_step_run"

    id: int | None = Field(default=None, primary_key=True)
    pipeline_run_id: int = Field(foreign_key="pipeline_run.id", index=True, ondelete="CASCADE")
    step_id: int | None = Field(default=None, foreign_key="pipeline_step.id", ondelete="SET NULL")
    position: int
    name: str
    kind: str
    status: str
    input: str = Field(default="", sa_type=Text)
    output: str | None = Field(default=None, sa_type=Text)
    error: str | None = Field(default=None, sa_type=Text)
    agent_run_id: str | None = Field(default=None, foreign_key="agent_run.run_id", ondelete="SET NULL")
    started_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    finished_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


# ------------------------------------------------------------------ copilot

class CopilotSessionTable(SQLModel, table=True):
    """An agent task delegated to Copilot CLI: the planning chat, then the
    execution. Also the worker queue of the executions (``queued`` rows) and
    of the planning turns (``planning_turn = 'queued'``)."""
    __tablename__ = "copilot_session"

    id: int | None = Field(default=None, primary_key=True)
    project_name: str = _project_fk(nullable=False)
    task_note: str
    repository: str = ""
    copilot_session_id: str = Field(unique=True)
    prompt: str = ""
    """The planning prompt chosen (a coding-agent/<name>.md); ``""`` = the default."""
    model: str = ""
    """Copilot's model for every turn; ``""`` = COPILOT_MODEL or Copilot's default."""
    status: str = Field(index=True)
    """``planning`` | ``queued`` | ``running`` | ``done`` | ``failed`` | ``cancelled``."""
    planning_turn: str | None = None
    """``queued`` | ``running`` | NULL: the planning turn in the worker's queue (only while ``planning``)."""
    cancel_requested: bool = False
    head_before: str | None = None
    head_after: str | None = None
    changed_files: list[str] = Field(default_factory=list, sa_type=JSON)
    premium_requests: int = 0
    error: str | None = Field(default=None, sa_type=Text)
    created_at: datetime = _timestamp(index=True)
    updated_at: datetime = _timestamp()
    started_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    finished_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


class CopilotMessageTable(SQLModel, table=True):
    __tablename__ = "copilot_message"

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="copilot_session.id", index=True, ondelete="CASCADE")
    role: str
    """``user`` | ``copilot`` | ``event``."""
    content: str = Field(sa_type=Text)
    created_at: datetime = _timestamp()


class CopilotTurnTable(SQLModel, table=True):
    """What one turn of a Copilot session used (observability). ``session_id``
    is a plain column, no FK: the history survives the session's deletion."""
    __tablename__ = "copilot_turn"

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(index=True)
    project_name: str = Field(index=True)
    task_note: str
    phase: str
    """``plan`` | ``execute``."""
    model: str = Field(default="", index=True)
    ok: bool = True
    cancelled: bool = False
    error: str | None = Field(default=None, sa_type=Text)
    duration_ms: int = 0
    premium_requests: float = 0.0
    nano_aiu: int = Field(default=0, sa_type=BigInteger)
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    api_duration_ms: int = 0
    created_at: datetime = _timestamp(index=True)


# ---------------------------------------------------------------------- RAG

class DocumentTable(SQLModel, table=True):
    """A data item of the project indexed for RAG: a note or an uploaded file
    in ``<MBARE_PILOT_HOME>/projects/<slug>/`` (never the code folder)."""
    __tablename__ = "document"
    __table_args__ = (UniqueConstraint("project_name", "path"),)

    id: int | None = Field(default=None, primary_key=True)
    project_name: str = _project_fk(nullable=False)
    path: str
    """Relative to the project's data folder (e.g. ``notes/setup.md``)."""
    source: str
    """``note`` | ``file``."""
    content_hash: str
    indexed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


class ChunkTable(SQLModel, table=True):
    __tablename__ = "chunk"

    id: int | None = Field(default=None, primary_key=True)
    document_id: int = Field(foreign_key="document.id", index=True, ondelete="CASCADE")
    project_name: str = _project_fk(nullable=False)
    position: int
    text: str = Field(sa_type=Text)
    embedding_model: str
    embedding: list[float] = Field(sa_column=Column(Vector()))
    """No fixed dimension: projects may use different embedding models."""


# ------------------------------------------------------------ runs + costs

class AgentRunTable(SQLModel, table=True):
    """Analytical facts of one agent run. The verbatim trace lives in Redis
    (keyspace agent-trace, same run_id)."""
    __tablename__ = "agent_run"

    run_id: str = Field(primary_key=True)
    project_name: str | None = Field(default=None, index=True)
    """Plain column, no FK: run history survives project removal."""
    origin: str = Field(index=True)
    """``chat`` | ``pipeline`` | ``manual``."""
    config_name: str = Field(index=True)
    role_name: str = Field(index=True)
    prompt_id: int
    prompt_version: int
    model: str
    ok: bool
    error: str | None = None
    latency_ms: float

    agent_input_tokens: int
    agent_output_tokens: int
    agent_cost_eur: float
    tool_input_tokens: int
    tool_output_tokens: int
    tool_cost_eur: float
    total_input_tokens: int
    total_output_tokens: int
    total_cached_tokens: int
    total_thinking_tokens: int
    total_cost_eur: float

    tool_names: str
    """Comma-separated names of the tools called, in call order."""
    created_at: datetime = _timestamp(index=True)


class ToolCallTable(SQLModel, table=True):
    """Analytical facts of one tool call (arguments and result stay in the
    Redis trace)."""
    __tablename__ = "tool_call"

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="agent_run.run_id", index=True, ondelete="CASCADE")
    position: int
    tool_name: str = Field(index=True)
    ok: bool
    error: str | None = None
    latency_ms: float
    input_tokens: int
    output_tokens: int
    cost_eur: float
    created_at: datetime = _timestamp(index=True)


class ChatModelTable(SQLModel, table=True):
    """The model catalog: provider + model id, price in EUR per 1M tokens,
    editable at runtime (Admin → Modelli)."""
    __tablename__ = "chat_model"

    provider: str = Field(primary_key=True)
    model: str = Field(primary_key=True)
    input_per_1m: float = 0.0
    output_per_1m: float = 0.0
    active: bool = True
