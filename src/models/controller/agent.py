"""Request/response models of the agents API (agents, roles, prompt versions,
tools, model choices). ``project_name`` None = global (Library)."""
from datetime import datetime

from pydantic import BaseModel, Field

from models.domain.agent import AgentConfig, AgentRole, SystemPrompt, ToolInfo


class AgentResponse(BaseModel):
    name: str
    project_name: str | None
    description: str
    role_name: str
    prompt_id: int
    prompt_version: int | None
    """None when the pinned prompt no longer exists."""
    model: str
    max_steps: int
    tool_names: list[str]
    blocked_reason: str | None
    """Why the agent cannot run right now (inactive role/prompt/model, ...); None = runnable."""

    @classmethod
    def from_config(cls, config: AgentConfig, prompt_version: int | None, blocked_reason: str | None) -> "AgentResponse":
        return cls(**config.model_dump(), prompt_version=prompt_version, blocked_reason=blocked_reason)


class AgentCreateRequest(BaseModel):
    name: str
    project_name: str | None = None
    description: str = ""
    role_name: str
    prompt_id: int
    model: str
    max_steps: int = 4
    tool_names: list[str] = Field(default_factory=list)


class AgentUpdateRequest(BaseModel):
    """Everything but the name and the scope, which are fixed at creation."""
    description: str = ""
    role_name: str
    prompt_id: int
    model: str
    max_steps: int = 4
    tool_names: list[str] = Field(default_factory=list)


class RoleResponse(BaseModel):
    name: str
    project_name: str | None
    description: str
    active: bool

    @classmethod
    def from_role(cls, role: AgentRole) -> "RoleResponse":
        return cls(**role.model_dump())


class RoleCreateRequest(BaseModel):
    name: str
    project_name: str | None = None
    description: str = ""


class RoleUpdateRequest(BaseModel):
    """Fields left out (None) are not changed."""
    description: str | None = None
    active: bool | None = None


class PromptResponse(BaseModel):
    id: int
    role_name: str
    version: int
    text: str
    active: bool
    created_at: datetime

    @classmethod
    def from_prompt(cls, prompt: SystemPrompt) -> "PromptResponse":
        return cls(**prompt.model_dump())


class PromptCreateRequest(BaseModel):
    text: str


class PromptVersionResponse(BaseModel):
    prompt: PromptResponse
    created: bool
    """False when the text was identical to the latest version (no new version)."""


class PromptUpdateRequest(BaseModel):
    active: bool


class ToolResponse(BaseModel):
    name: str
    description: str
    available: bool

    @classmethod
    def from_tool(cls, tool: ToolInfo) -> "ToolResponse":
        return cls(**tool.model_dump())


class ModelChoicesResponse(BaseModel):
    """What a model picker offers: the active models, plus the current one when
    it is no longer usable (listed in ``choices`` but not in ``usable``)."""
    choices: list[str]
    usable: list[str]
