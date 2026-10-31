"""Definitions as files (models/domain/definitions.py): agents, chatbots and
automations written as YAML under ``<MBARE_PILOT_HOME>/definition/``, applied
to a project on request:

- ``global-agent.yml``: agents of the Library (global);
- ``project/<slug>/agent.yml``: the project's agents;
- ``project/<slug>/chat-bots.yml``: the project's chatbots, plus those of
  ``global-chat-bots.yml`` with a name the project does not use (the older
  single-chatbot files ``chat-bot.yml`` / ``global-chat-bot.yml`` are still read);
- ``project/<slug>/automation.yml``: the project's automations, plus those of
  ``global-automation.yml`` with a name the project does not use.

``sync(project)`` validates every element with the same rules as the API (the
same services do the work) and creates or updates it, matched by name: the
file wins over changes made from the UI. What is not in the files is left as it
is. An element with errors is skipped and reported; the others are applied.
An empty file (or one with only comments) defines nothing.

``preview(project)`` lists what the files define without applying anything
(new or already there, or the error), and ``sync(project, only)`` can apply
just the elements chosen from it.

At startup ``seed_global_agents()`` creates the agents of ``global-agent.yml``
that do not exist yet (a new installation has them; changes made from the UI
stay until the next sync), and ``seed_default_chatbots(projects)`` the
default chatbots (domain/chat/chatbots_default.py) that a project misses, by
name: also when a project is created."""
from collections.abc import Callable, Collection
from dataclasses import dataclass
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError as PydanticValidationError

from core.error import AppError, NotFoundError, ValidationError
from core.observability import LogPrefix, log_warning, observed
from domain.chat.chatbots_default import DEFAULT_CHATBOTS
from domain.pipeline.graph import linear_edges
from domain.project.data_paths import (
    AGENTS_FILE,
    AUTOMATIONS_FILE,
    CHATBOT_FILE,
    CHATBOTS_FILE,
    GLOBAL_AGENTS_FILE,
    GLOBAL_AUTOMATIONS_FILE,
    GLOBAL_CHATBOT_FILE,
    GLOBAL_CHATBOTS_FILE,
    data_file_name,
    project_definitions,
)
from models.domain.agent import AgentConfig, AgentRole
from models.domain.chatbot import KIND_TOOLS
from models.domain.definitions import (
    AgentFile,
    AutomationFile,
    ChatbotFile,
    DefinitionEntry,
    DefinitionKey,
    DefinitionKind,
    DefinitionState,
    StepFile,
    SyncItem,
    SyncOutcome,
    SyncReport,
)
from models.domain.pipeline import Pipeline, PipelineEdge, PipelineStep, StepAgent, StepKind
from service.agent_config_service import AgentConfigService
from service.chatbot_service import ChatbotService
from service.pipeline_service import PipelineService
from service.store.agent_store import AgentStore
from service.store.project_store import ProjectStore
from service.store_service import StoreService

_AGENTS_KEY = "agents"
_AUTOMATIONS_KEY = "automations"
_CHATBOTS_KEY = "chatbots"


class DefinitionService:

    def __init__(self, store_service: StoreService, projects: ProjectStore, agent_store: AgentStore, agent_config_service: AgentConfigService,
                 chatbot_service: ChatbotService, pipeline_service: PipelineService):
        self._store = store_service
        self._projects = projects
        self._agent_store = agent_store
        self._agents = agent_config_service
        self._chatbots = chatbot_service
        self._pipelines = pipeline_service

    @observed(LogPrefix.DEFINITION_SERVICE)
    def sync(self, project_name: str, only: Collection[DefinitionKey] | None = None) -> SyncReport:
        """Global agents, the project's agents, its chatbot, its automations;
        ``only`` = just these elements (as ``preview`` lists them), None = all."""
        chosen = None if only is None else {DefinitionKey(kind=key.kind, file=key.file, name=key.name) for key in only}  # entries too
        items = [element.apply_to_item() for element in self._elements(project_name) if chosen is None or element.key in chosen]
        return SyncReport(project_name=project_name, items=items)

    def preview(self, project_name: str) -> list[DefinitionEntry]:
        """What the files define, nothing applied: each element new or already
        there (found by name: a sync would update it), or why it would fail."""
        return [self._entry(project_name, element) for element in self._elements(project_name)]

    def _elements(self, project_name: str) -> list["_Element"]:
        """Every element of the project's files, in the order a sync applies them."""
        if self._projects.get(project_name) is None:
            raise NotFoundError(f"Progetto non trovato: {project_name}")
        folder = project_definitions(project_name)
        elements = self._list(DefinitionKind.AGENT, GLOBAL_AGENTS_FILE, _AGENTS_KEY, AgentFile, lambda spec: self._sync_agent(None, spec))
        elements += self._list(DefinitionKind.AGENT, f"{folder}/{AGENTS_FILE}", _AGENTS_KEY, AgentFile, lambda spec: self._sync_agent(project_name, spec))
        elements += self._chatbots_of(project_name, folder)
        elements += self._automations(project_name, folder)
        return elements

    def _entry(self, project_name: str, element: "_Element") -> DefinitionEntry:
        common = dict(kind=element.kind, file=element.file, name=element.name)
        try:
            element.validate()
        except PydanticValidationError as exc:
            return DefinitionEntry(**common, state=DefinitionState.ERROR, message=_first_error(exc))
        except AppError as exc:
            return DefinitionEntry(**common, state=DefinitionState.ERROR, message=str(exc))
        if element.kind is DefinitionKind.AGENT:
            exists = self._agent_store.get_config(element.name) is not None
        elif element.kind is DefinitionKind.CHATBOT:
            exists = any(bot.name.lower() == element.name.lower() for bot in self._chatbots.list_chatbots(project_name))
        else:
            exists = any(pipeline.name.lower() == element.name.lower() for pipeline in self._pipelines.list_pipelines(project_name))
        return DefinitionEntry(**common, state=DefinitionState.EXISTS if exists else DefinitionState.NEW)

    @observed(LogPrefix.DEFINITION_SERVICE)
    def seed_global_agents(self) -> list[SyncItem]:
        """At startup: the agents of global-agent.yml that do not exist yet; the
        existing ones are left as they are. Errors are logged, never raised:
        a broken file must not stop the app."""
        elements = self._list(DefinitionKind.AGENT, GLOBAL_AGENTS_FILE, _AGENTS_KEY, AgentFile, self._create_missing_global_agent)
        items = [element.apply_to_item() for element in elements]
        for item in items:
            if item.outcome is SyncOutcome.ERROR:
                log_warning(LogPrefix.DEFINITION_SERVICE, "%s · %s: %s", item.file, item.name or "?", item.message)
        return items

    def _create_missing_global_agent(self, spec: AgentFile) -> SyncOutcome:
        if self._agent_store.get_config(spec.name) is not None:
            return SyncOutcome.UNCHANGED
        return self._sync_agent(None, spec)

    @observed(LogPrefix.DEFINITION_SERVICE)
    def seed_default_chatbots(self, project_names: list[str]) -> int:
        """The default chatbots the projects miss (by name, case-insensitive);
        the existing ones are left as they are. Errors (e.g. the model not in
        the catalog) are logged, never raised: they must not stop the app.
        Returns how many were created."""
        created = 0
        for project_name in project_names:
            names = {bot.name.lower() for bot in self._chatbots.list_chatbots(project_name)}
            for spec in DEFAULT_CHATBOTS:
                if spec.name.lower() in names:
                    continue
                try:
                    self._sync_chatbot(project_name, spec, "")
                    created += 1
                except Exception as exc:  # also the API and the worker starting together: the name is unique in the DB
                    log_warning(LogPrefix.DEFINITION_SERVICE, "chatbot di default %s · %s: %s", project_name, spec.name, exc)
        return created

    # ---------------------------------------------------------------- files
    def _list(self, kind: DefinitionKind, path: str, key: str, schema: type[BaseModel], sync: Callable[[Any], SyncOutcome],
              skip: Callable[[dict], bool] = lambda raw: False) -> list["_Element"]:
        """One element per item of the file's ``key`` list (``skip`` leaves some out)."""
        try:
            raw = self._read(path)
            if raw is None:
                return []
            elements = raw.get(key)
            if not isinstance(elements, list):
                raise ValidationError(f"il file deve avere la lista «{key}:».")
        except AppError as exc:
            return [_Element(kind, path, None, None, schema, sync, error=str(exc))]
        return [
            _Element(kind, path, element, index, schema, sync)
            for index, element in enumerate(elements, start=1)
            if not (isinstance(element, dict) and skip(element))
        ]

    def _read(self, path: str) -> dict | None:
        """The YAML of a definition file; None when missing or empty."""
        text = self._store.read_definition(path)
        if text is None:
            return None
        try:
            raw = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ValidationError(f"YAML non valido: {exc}") from exc
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise ValidationError("il file deve contenere dei campi (nome: valore).")
        return raw

    # --------------------------------------------------------------- agents
    def _sync_agent(self, project_name: str | None, spec: AgentFile) -> SyncOutcome:
        """The agent (``project_name`` None = global), its role (created when
        missing, in the same scope) and its prompt (a new version when the text
        changed)."""
        scope = f"del progetto {project_name}" if project_name else "globale"
        role = self._agent_store.get_role(spec.role)
        if role is None:
            self._agents.save_role(AgentRole(name=spec.role, project_name=project_name), create=True)
        elif role.project_name != project_name:
            raise ValidationError(f"Il ruolo {spec.role} esiste già ma non è {scope}: usa un altro nome.")
        existing = self._agent_store.get_config(spec.name)
        if existing is not None and existing.project_name != project_name:
            raise ValidationError(f"Esiste già un agente {spec.name} che non è {scope}: usa un altro nome.")
        prompt = self._agents.create_prompt_version(spec.role, spec.system_prompt)  # same text = same version
        config = AgentConfig(
            name=spec.name, project_name=project_name, description=spec.description.strip(), role_name=spec.role,
            prompt_id=prompt.id, model=spec.model, max_steps=spec.max_steps, tool_names=spec.tools,
        )
        if existing == config:
            return SyncOutcome.UNCHANGED
        self._agents.save_config(config, create=existing is None)
        return SyncOutcome.CREATED if existing is None else SyncOutcome.UPDATED

    # -------------------------------------------------------------- chatbot
    def _chatbots_of(self, project_name: str, folder: str) -> list["_Element"]:
        """The project's chatbots (chat-bots.yml, then the single chat-bot.yml),
        then the global ones (global-chat-bots.yml, global-chat-bot.yml) with a
        name the project does not use: a base for every project."""
        def sync(prompt_folder: str) -> Callable[[ChatbotFile], SyncOutcome]:
            return lambda spec: self._sync_chatbot(project_name, spec, prompt_folder)

        own = self._list(DefinitionKind.CHATBOT, f"{folder}/{CHATBOTS_FILE}", _CHATBOTS_KEY, ChatbotFile, sync(folder))
        own += self._single(DefinitionKind.CHATBOT, f"{folder}/{CHATBOT_FILE}", ChatbotFile, sync(folder))
        names = {element.name.lower() for element in own if element.name}
        not_own = lambda raw: str(raw.get("name", "")).strip().lower() in names  # noqa: E731
        shared = self._list(DefinitionKind.CHATBOT, GLOBAL_CHATBOTS_FILE, _CHATBOTS_KEY, ChatbotFile, sync(""), skip=not_own)
        shared += self._single(DefinitionKind.CHATBOT, GLOBAL_CHATBOT_FILE, ChatbotFile, sync(""), skip=not_own)
        return own + shared

    def _single(self, kind: DefinitionKind, path: str, schema: type[BaseModel], sync: Callable[[Any], SyncOutcome],
                skip: Callable[[dict], bool] = lambda raw: False) -> list["_Element"]:
        """A file that is one element (no list); none when missing, empty or skipped."""
        try:
            raw = self._read(path)
        except AppError as exc:
            return [_Element(kind, path, None, None, schema, sync, error=str(exc))]
        return [] if raw is None or skip(raw) else [_Element(kind, path, raw, None, schema, sync)]

    def _sync_chatbot(self, project_name: str, spec: ChatbotFile, prompt_folder: str) -> SyncOutcome:
        """The project's chatbot with this name (case-insensitive), else a new one."""
        prompt = spec.system_prompt
        if prompt is None:
            path = f"{prompt_folder}/{data_file_name(spec.system_prompt_file)}".lstrip("/")
            prompt = self._store.read_definition(path)
            if prompt is None or not prompt.strip():
                raise ValidationError(f"File del prompt non trovato o vuoto: {path}")
        values = dict(
            name=spec.name,
            kind=spec.kind,
            system_prompt=prompt.strip(),
            model=spec.model,
            description=spec.description.strip(),
            max_steps=spec.max_steps,
            tool_names=list(KIND_TOOLS.get(spec.kind, spec.tools)),  # a kind's fixed tools: compared as saved
        )
        current = next((bot for bot in self._chatbots.list_chatbots(project_name) if bot.name.lower() == spec.name.lower()), None)
        if current is None:
            self._chatbots.create_chatbot(project_name, **values)
            return SyncOutcome.CREATED
        if {key: getattr(current, key) for key in values} == values:
            return SyncOutcome.UNCHANGED
        self._chatbots.update_chatbot(current.id, **values)
        return SyncOutcome.UPDATED

    # ---------------------------------------------------------- automations
    def _automations(self, project_name: str, folder: str) -> list["_Element"]:
        """The project's automations, then the global ones it does not redefine (by name)."""
        sync = lambda spec: self._sync_automation(project_name, spec)  # noqa: E731
        path = f"{folder}/{AUTOMATIONS_FILE}"
        items = self._list(DefinitionKind.AUTOMATION, path, _AUTOMATIONS_KEY, AutomationFile, sync)
        try:
            own = {str(element.get("name", "")).strip().lower()
                   for element in (self._read(path) or {}).get(_AUTOMATIONS_KEY) or [] if isinstance(element, dict)}
        except AppError:
            own = set()
        return items + self._list(DefinitionKind.AUTOMATION, GLOBAL_AUTOMATIONS_FILE, _AUTOMATIONS_KEY, AutomationFile, sync,
                                  skip=lambda raw: str(raw.get("name", "")).strip().lower() in own)

    def _sync_automation(self, project_name: str, spec: AutomationFile) -> SyncOutcome:
        """Steps are matched by name with the saved ones: they keep their id
        (history, prompt versions) and their place in the graph editor."""
        current = next((p for p in self._pipelines.list_pipelines(project_name) if p.name.lower() == spec.name.lower()), None)
        previous = {step.name.lower(): step for step in current.steps} if current else {}
        steps = [_step(step, previous.get(step.name.lower())) for step in spec.steps]
        edges = [PipelineEdge(source=e.source, target=e.target, condition=e.condition, value=e.value) for e in spec.edges or []]
        values = dict(name=spec.name, description=spec.description, active=spec.active, steps=steps, edges=edges)
        if current is None:
            self._pipelines.create_pipeline(project_name, **values)
            return SyncOutcome.CREATED
        if _shape(current) == _shape(Pipeline(project_name=project_name, **{**values, "edges": edges or linear_edges(steps)})):
            return SyncOutcome.UNCHANGED
        self._pipelines.update_pipeline(current.id, **values)
        return SyncOutcome.UPDATED


@dataclass
class _Element:
    """One element of a definition file, to preview or apply. ``raw`` None =
    the file itself could not be read (``error`` says why)."""
    kind: DefinitionKind
    file: str
    raw: Any
    index: int | None
    schema: type[BaseModel]
    apply: Callable[[Any], SyncOutcome] | None
    error: str = ""

    @property
    def name(self) -> str | None:
        """What it defines; ``elemento N`` without a name, None for a broken file."""
        if isinstance(self.raw, dict) and self.raw.get("name"):
            return str(self.raw["name"])
        return f"elemento {self.index}" if self.index else None

    @property
    def key(self) -> DefinitionKey:
        return DefinitionKey(kind=self.kind, file=self.file, name=self.name)

    def validate(self) -> BaseModel:
        """The element as its schema; ValidationError or pydantic's error otherwise."""
        if self.error:
            raise ValidationError(self.error)
        if not isinstance(self.raw, dict):
            raise ValidationError("ogni elemento deve contenere dei campi (nome: valore).")
        return self.schema.model_validate(self.raw)

    def apply_to_item(self) -> SyncItem:
        """Validate and apply it; its errors become the item's message."""
        try:
            spec = self.validate()
            outcome = self.apply(spec)
        except PydanticValidationError as exc:
            return SyncItem(kind=self.kind, file=self.file, name=self.name, outcome=SyncOutcome.ERROR, message=_first_error(exc))
        except AppError as exc:
            return SyncItem(kind=self.kind, file=self.file, name=self.name, outcome=SyncOutcome.ERROR, message=str(exc))
        return SyncItem(kind=self.kind, file=self.file, name=spec.name, outcome=outcome)


def _step(spec: StepFile, previous: PipelineStep | None) -> PipelineStep:
    common = dict(
        id=previous.id if previous else None,
        name=spec.name,
        input_template=spec.input,
        position_x=previous.position_x if previous else 0.0,
        position_y=previous.position_y if previous else 0.0
    )
    if spec.function is not None:
        return PipelineStep(kind=StepKind.FUNCTION, function_name=spec.function, params=spec.params, **common)
    if spec.agent is not None:
        return PipelineStep(kind=StepKind.AGENT_CONFIG, agent_config_name=spec.agent, **common)
    agent = StepAgent(system_prompt=spec.system_prompt, model=spec.model, max_steps=spec.max_steps, tool_names=spec.tools)
    return PipelineStep(kind=StepKind.AGENT, agent=agent, **common)


def _shape(pipeline: Pipeline) -> tuple:
    """What a file defines of an automation: no ids, positions or prompt versions."""
    steps = [
        (
         step.name,
         step.kind,
         step.input_template,
         step.agent_config_name,
         step.function_name,
         step.params,
         (
            step.agent.system_prompt,
            step.agent.model,
            step.agent.max_steps,
            list(step.agent.tool_names)
         ) if step.agent else None
        )
    for step in pipeline.steps
    ]
    edges = sorted((edge.source, edge.target, edge.condition.value, edge.value) for edge in pipeline.edges)
    return pipeline.name, pipeline.description.strip(), pipeline.active, steps, edges


def _first_error(exc: PydanticValidationError) -> str:
    """The first validation error as "field: message" (the file's names)."""
    error = exc.errors()[0]
    field = ".".join(str(part) for part in error["loc"])
    message = error["msg"].removeprefix("Value error, ")
    return f"{field}: {message}" if field else message
