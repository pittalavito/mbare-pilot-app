"""Definitions as files: agents, chatbots and automations written as YAML
under ``<MBARE_PILOT_HOME>/definition/`` (layout in domain/project/data_paths.py):
``agent.yml`` / ``global-agent.yml`` hold a list ``agents:`` of ``AgentFile``,
``automation.yml`` / ``global-automation.yml`` a list ``automations:`` of
``AutomationFile``, ``chat-bots.yml`` / ``global-chat-bots.yml`` a list
``chatbots:`` of ``ChatbotFile`` (``chat-bot.yml`` / ``global-chat-bot.yml``: one),
``coding-agent.yml`` / ``global-coding-agent.yml`` one ``CodingAgentFile``
(read by CopilotService at every use, never synced).

DefinitionService validates them and applies them on request ("sync"): what
is in the files is created or updated, matched by name, and the file wins over
changes made from the UI; what is not in the files is left as it is. Unknown
fields are errors (``extra="forbid"``): a typo never passes silently."""
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

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
    """An element of ``chatbots:`` (or the whole ``chat-bot.yml``): a chatbot of
    the project, matched by name. The prompt is written here or in a file next
    to this one (``system_prompt_file``), used as it is."""
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


class ModelPriceFile(_File):
    """USD per 1M tokens, as GitHub's "Models and pricing for GitHub Copilot" lists them."""
    input: float = Field(ge=0)
    cached_input: float = Field(ge=0)
    cache_write: float | None = Field(default=None, ge=0)
    """None where GitHub lists none."""
    output: float = Field(ge=0)


class LongContextPriceFile(ModelPriceFile):
    """The tier above ``above`` input tokens."""
    above: int = Field(gt=0)


class ModelFile(ModelPriceFile):
    """An element of ``models:`` with its price; a plain name has none."""
    name: Prompt
    note: str = ""
    input: float | None = Field(default=None, ge=0)
    cached_input: float | None = Field(default=None, ge=0)
    output: float | None = Field(default=None, ge=0)
    long_context: LongContextPriceFile | None = None

    @model_validator(mode="after")
    def _whole_price(self) -> "ModelFile":
        if (self.input is None) != (self.output is None) or (self.cached_input is not None and self.input is None):
            raise ValueError(f"modello {self.name}: scrivi input, cached_input e output insieme (o nessuno)")
        if self.long_context is not None and self.input is None:
            raise ValueError(f"modello {self.name}: long_context vuole anche il prezzo base")
        return self


class CodingAgentFile(_File):
    """``global-coding-agent.yml`` (and ``project/<slug>/coding-agent.yml``,
    whose fields replace the global ones): what the app tells Copilot.
    ``plan_prompt`` is the first planning turn (``{task}`` = the task's
    markdown), ``execute_prompt`` the turn that starts the execution,
    ``denied_tools`` the ``--deny-tool`` of the execution (e.g. ``shell(git
    commit)``): the whole list, nothing is added by the code. A prompt can be
    in a file next to this one (``*_prompt_file``), used as it is."""
    plan_prompt: Prompt | None = None
    plan_prompt_file: str | None = None
    execute_prompt: Prompt | None = None
    execute_prompt_file: str | None = None
    references_prompt: Prompt | None = None
    """Added to the first planning turn when the task links references:
    ``{task_folder}`` = the folder with the task and its references as files."""
    references_prompt_file: str | None = None
    denied_tools: list[Prompt] | None = None
    models: list[ModelFile] | None = None
    """Copilot models to choose from when delegating (``--model``): a name, or
    ``{name, input, cached_input, cache_write, output, note, long_context}``."""

    @field_validator("models", mode="before")
    @classmethod
    def _plain_names(cls, value: Any) -> Any:
        """A plain name is a model without a price (errors then name the right fields)."""
        return [{"name": item} if isinstance(item, str) else item for item in value] if isinstance(value, list) else value

    @model_validator(mode="after")
    def _one_source(self) -> "CodingAgentFile":
        for name in ("plan_prompt", "execute_prompt", "references_prompt"):
            if getattr(self, name) is not None and getattr(self, f"{name}_file") is not None:
                raise ValueError(f"scrivi {name} oppure {name}_file (uno dei due)")
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


class DefinitionKey(BaseModel):
    """One element of the definition files, as a preview lists it and a sync
    can choose it: kind, file (relative to ``definition/``) and name."""
    model_config = ConfigDict(frozen=True)

    kind: DefinitionKind
    file: str
    name: str | None


class DefinitionState(StrEnum):
    NEW = "new"
    """Nothing with that name yet: a sync would create it."""
    EXISTS = "exists"
    """Already there (by name): a sync would update it, the file wins (or leave it unchanged)."""
    ERROR = "error"
    """The element (or its file) is broken: a sync would skip it."""


class DefinitionEntry(DefinitionKey):
    """An element of the preview: what a sync would do with it."""
    model_config = ConfigDict(frozen=True)

    state: DefinitionState
    message: str = ""


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
