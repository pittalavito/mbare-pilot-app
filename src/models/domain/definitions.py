"""Definitions as files: agents, chatbots and automations written as YAML
under ``<MBARE_PILOT_HOME>/definition/`` (layout in domain/project/data_paths.py):
``agent.yml`` / ``global-agent.yml`` hold a list ``agents:`` of ``AgentFile``,
``automation.yml`` / ``global-automation.yml`` a list ``automations:`` of
``AutomationFile``, ``chat-bot.yml`` / ``global-chat-bot.yml`` one ``ChatbotFile``.

DefinitionService validates them and applies them on request ("sync"): what
is in the files is created or updated, matched by name, and the file wins over
changes made from the UI; what is not in the files is left as it is. Unknown
fields are errors (``extra="forbid"``): a typo never passes silently."""
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from models.domain.agent import Name
from models.domain.chat import ModelKey
from models.domain.pipeline import INPUT, EdgeConditionKind

Prompt = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class _File(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentFile(_File):
    """An element of ``agents:``: an agent of the project (or of the Library, in
    global-agent.yml). Its role is created when missing, in the same scope; a
    changed ``system_prompt`` becomes the role's next prompt version."""
    name: Name
    description: str = ""
    role: Name
    model: ModelKey
    max_steps: int = Field(default=4, ge=1, le=50)
    tools: list[str] = Field(default_factory=list)
    system_prompt: Prompt


class ChatbotFile(_File):
    """``chat-bot.yml`` (or ``global-chat-bot.yml``): the project's chatbot, one
    per project. The prompt is written here or in a file next to this one
    (``system_prompt_file``), used as it is."""
    name: Name
    description: str = ""
    model: ModelKey
    max_steps: int = Field(default=4, ge=1, le=50)
    tools: list[str] = Field(default_factory=list)
    system_prompt: Prompt | None = None
    system_prompt_file: str | None = None

    @model_validator(mode="after")
    def _one_prompt(self) -> "ChatbotFile":
        if (self.system_prompt is None) == (self.system_prompt_file is None):
            raise ValueError("scrivi system_prompt oppure system_prompt_file (uno dei due)")
        return self


class StepFile(_File):
    """A step of an automation: exactly one of ``function`` (with its
    ``params``), ``agent`` (an agent of the project or of the Library) or an own
    agent (``system_prompt`` + ``model``, optional ``tools`` and ``max_steps``)."""
    name: Name
    input: str = INPUT
    """What the step receives: ``{input}``, ``{pipeline_input}``, ``{nodo:Nome}``."""
    function: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    agent: str | None = None
    system_prompt: Prompt | None = None
    model: ModelKey | None = None
    max_steps: int = Field(default=4, ge=1, le=50)
    tools: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _one_kind(self) -> "StepFile":
        kinds = [self.function is not None, self.agent is not None, self.system_prompt is not None]
        if sum(kinds) != 1:
            raise ValueError(f"step {self.name}: scrivi uno solo tra function, agent e system_prompt")
        if self.params and self.function is None:
            raise ValueError(f"step {self.name}: params vale solo con function")
        if self.system_prompt is not None and self.model is None:
            raise ValueError(f"step {self.name}: un agente proprio vuole anche model")
        if self.system_prompt is None and (self.model is not None or self.tools):
            raise ValueError(f"step {self.name}: model e tools valgono solo con system_prompt")
        return self


class EdgeFile(_File):
    """``{from: Stato, to: Riassumi, if: contains, value: OK}``; ``from: input``
    is the run's input. Without ``if`` the edge always passes."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    source: str = Field(alias="from")
    target: str = Field(alias="to")
    condition: EdgeConditionKind = Field(default=EdgeConditionKind.ALWAYS, alias="if")
    value: str = ""


class AutomationFile(_File):
    """An element of ``automations:``: an automation of the project. Without
    ``edges`` the steps form a chain, in their order."""
    name: Name
    description: str = ""
    active: bool = True
    steps: list[StepFile] = Field(min_length=1)
    edges: list[EdgeFile] | None = None


class DefinitionKind(StrEnum):
    AGENT = "agent"
    CHATBOT = "chatbot"
    AUTOMATION = "automation"


class SyncOutcome(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    ERROR = "error"
    """The file was skipped (the others are applied anyway)."""


class SyncItem(BaseModel):
    kind: DefinitionKind
    file: str
    """Relative to ``definition/``, e.g. ``project/acme/agent.yml``."""
    name: str | None = None
    """What the element defines; None when the file could not be read."""
    outcome: SyncOutcome
    message: str = ""


class SyncReport(BaseModel):
    project_name: str
    items: list[SyncItem] = Field(default_factory=list)
