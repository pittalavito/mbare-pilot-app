"""Definitions as files (models/domain/definitions.py): agents, chatbots and
automations written as YAML, in two layers: the app's defaults
(``resource/definition``) and the user's (``<MBARE_PILOT_HOME>/definition/``).
In the global files the user's elements win **by name** over the app's (the
user's ``global-chat-bots.yml`` may hold just the Refiner changed); the
projects' files are the user's only. The files:

- ``global-agent.yml``: agents of the Library (global);
- ``project/<slug>/agent.yml``: the project's agents;
- ``project/<slug>/chat-bots.yml``: the project's chatbots, plus those of
  ``global-chat-bots.yml`` with a name the project does not use;
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

At startup ``sync_at_startup(projects)`` applies every file to every project
(created or updated; what the files do not define is left as it is): the
defaults follow the files, a new installation has them. A chatbot of the
files changed from the UI is written back to the user's layer
(``save_chatbot``: it becomes «tuo» and wins on the next startup);
``revert_chatbot`` removes it from there («↩ Torna al default»). Every entry
of ``preview`` says where it comes from (``origin``: app, tuo, progetto)."""
from collections.abc import Callable, Collection
from dataclasses import dataclass
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError as PydanticValidationError

from core.error import AppError, NotFoundError, ValidationError
from core.observability import LogPrefix, log_warning, observed
from domain.pipeline import yaml_format
from domain.pipeline.graph import linear_edges
from domain.project.data_paths import (
    AGENTS_FILE,
    AUTOMATIONS_FILE,
    CHATBOTS_FILE,
    GLOBAL_AGENTS_FILE,
    GLOBAL_AUTOMATIONS_FILE,
    GLOBAL_CHATBOTS_FILE,
    data_file_name,
    project_definitions,
)
from models.domain.agent import AgentConfig, AgentRole
from models.domain.chatbot import Chatbot
from models.domain.definitions import (
    AgentFile,
    AutomationFile,
    ChatbotFile,
    DefinitionEntry,
    DefinitionKey,
    DefinitionKind,
    DefinitionState,
    SyncItem,
    SyncOutcome,
    SyncReport,
)
from models.domain.pipeline import Pipeline
from service.agent_config_service import AgentConfigService
from service.chatbot_service import ChatbotService
from service.pipeline_service import PipelineService
from service.store.agent_store import AgentStore
from service.store.definition_store import APP, USER, DefinitionStore
from service.store.project_store import ProjectStore

_AGENTS_KEY = "agents"
_AUTOMATIONS_KEY = "automations"
_CHATBOTS_KEY = "chatbots"
_MERGED = {GLOBAL_AGENTS_FILE: _AGENTS_KEY, GLOBAL_CHATBOTS_FILE: _CHATBOTS_KEY, GLOBAL_AUTOMATIONS_FILE: _AUTOMATIONS_KEY}
"""The global files whose lists are merged by name across the two layers."""
ORIGIN_PROJECT = "progetto"


class DefinitionService:

    def __init__(self, definitions: DefinitionStore, projects: ProjectStore, agent_store: AgentStore, agent_config_service: AgentConfigService,
                 chatbot_service: ChatbotService, pipeline_service: PipelineService):
        self._definitions = definitions
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
        try:
            origin = self.origin(element.file, element.name)
        except AppError:
            origin = USER  # a broken file of the user's layer
        common = dict(kind=element.kind, file=element.file, name=element.name, origin=origin)
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
    def sync_at_startup(self, project_names: list[str]) -> list[SyncItem]:
        """At startup (and for a new project): the global agents, then every project's files, created or updated.
        Errors are logged, never raised: a broken file must not stop the app."""
        items = [element.apply_to_item() for element in self._global_agents()]
        for project_name in project_names:
            try:
                items += [element.apply_to_item() for element in self._elements(project_name) if element.file != GLOBAL_AGENTS_FILE]
            except AppError as exc:
                log_warning(LogPrefix.DEFINITION_SERVICE, "definizioni di %s: %s", project_name, exc)
        for item in items:
            if item.outcome is SyncOutcome.ERROR:
                log_warning(LogPrefix.DEFINITION_SERVICE, "%s · %s: %s", item.file, item.name or "?", item.message)
        return items

    def _global_agents(self) -> list["_Element"]:
        return self._list(DefinitionKind.AGENT, GLOBAL_AGENTS_FILE, _AGENTS_KEY, AgentFile, lambda spec: self._sync_agent(None, spec))

    # --------------------------------------------------------------- origin
    def origin(self, file: str, name: str | None) -> str:
        """Where an element comes from: ``progetto`` (a project's file), ``tuo`` (the user's layer) or ``app``."""
        if file.startswith("project/"):
            return ORIGIN_PROJECT
        mine, _ = self._definitions.read_layers(file)
        names = _names(_load(mine)) if mine is not None else {}
        return USER if name and name.lower() in names.get(_list_key(file), set()) else APP

    def chatbot_origin(self, project_name: str, name: str) -> str | None:
        """The origin of a project's chatbot by name; None for one created from the UI (not in the files)."""
        element = next((item for item in self._chatbots_of(project_name, project_definitions(project_name))
                        if item.name and item.name.lower() == name.lower()), None)
        return self.origin(element.file, element.name) if element else None

    @observed(LogPrefix.DEFINITION_SERVICE)
    def save_chatbot(self, project_name: str, chatbot: Chatbot) -> str | None:
        """A chatbot of the files changed from the UI, written back as a file element: into the project's
        ``chat-bots.yml`` when it comes from there, else into the user's ``global-chat-bots.yml`` (it wins over the
        app's for every project). None (nothing written) for a chatbot created from the UI."""
        origin = self.chatbot_origin(project_name, chatbot.name)
        if origin is None:
            return None
        path = f"{project_definitions(project_name)}/{CHATBOTS_FILE}" if origin == ORIGIN_PROJECT else GLOBAL_CHATBOTS_FILE
        element = {"name": chatbot.name, "kind": chatbot.kind.value, "tools": list(chatbot.tool_names), "description": chatbot.description,
                   "model": chatbot.model, "max_steps": chatbot.max_steps, "system_prompt": chatbot.system_prompt}
        mine, _ = self._definitions.read_layers(path)
        data = _load(mine) if mine is not None else {}
        items = [item for item in data.get(_CHATBOTS_KEY) or [] if not (isinstance(item, dict) and str(item.get("name", "")).lower() == chatbot.name.lower())]
        self._definitions.save_definition(path, _dump({**data, _CHATBOTS_KEY: [*items, element]}))
        return path

    @observed(LogPrefix.DEFINITION_SERVICE)
    def revert_chatbot(self, project_name: str, name: str) -> SyncItem:
        """«↩ Torna al default»: the chatbot out of the user's ``global-chat-bots.yml``, the app's applied again."""
        mine, app = self._definitions.read_layers(GLOBAL_CHATBOTS_FILE)
        if app is None or name.lower() not in _names(_load(app)).get(_CHATBOTS_KEY, set()):
            raise NotFoundError(f"{name} non è un chatbot dell'app: non ha un default.")
        data = _load(mine) if mine is not None else {}
        items = [item for item in data.get(_CHATBOTS_KEY) or [] if not (isinstance(item, dict) and str(item.get("name", "")).lower() == name.lower())]
        if items or set(data) - {_CHATBOTS_KEY}:
            self._definitions.save_definition(GLOBAL_CHATBOTS_FILE, _dump({**data, _CHATBOTS_KEY: items}))
        else:
            self._definitions.delete_definition(GLOBAL_CHATBOTS_FILE)
        element = next(item for item in self._chatbots_of(project_name, project_definitions(project_name))
                       if item.name and item.name.lower() == name.lower())
        return element.apply_to_item()

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
        """The YAML of a definition file; None when missing or empty. A global file's list is the app's with the
        user's elements in place of the ones with the same name (and the user's new ones after)."""
        mine, app = self._definitions.read_layers(path)
        if path not in _MERGED:
            return _load(mine if mine is not None else app)
        user_data, app_data = _load(mine), _load(app)
        if user_data is None or app_data is None:
            return user_data if user_data is not None else app_data
        key = _MERGED[path]
        theirs, ours = app_data.get(key) or [], user_data.get(key) or []
        if not isinstance(theirs, list) or not isinstance(ours, list):
            raise ValidationError(f"il file deve avere la lista «{key}:».")
        by_name = {str(item.get("name", "")).lower(): item for item in ours if isinstance(item, dict) and item.get("name")}
        merged = [by_name.pop(str(item.get("name", "")).lower(), item) if isinstance(item, dict) else item for item in theirs]
        rest = [item for item in ours if not (isinstance(item, dict) and str(item.get("name", "")).lower() in
                                             {str(other.get("name", "")).lower() for other in merged if isinstance(other, dict)})]
        return {**app_data, **user_data, key: merged + rest}

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
            prompt_id=prompt.id, model=spec.model, max_steps=spec.max_steps, tool_names=spec.tools, output=spec.output,
        )
        if existing == config:
            return SyncOutcome.UNCHANGED
        self._agents.save_config(config, create=existing is None)
        return SyncOutcome.CREATED if existing is None else SyncOutcome.UPDATED

    # -------------------------------------------------------------- chatbot
    def _chatbots_of(self, project_name: str, folder: str) -> list["_Element"]:
        """The project's chatbots (chat-bots.yml), then the global ones
        (global-chat-bots.yml) with a name the project does not use: a base for every project."""
        def sync(prompt_folder: str) -> Callable[[ChatbotFile], SyncOutcome]:
            return lambda spec: self._sync_chatbot(project_name, spec, prompt_folder)

        own = self._list(DefinitionKind.CHATBOT, f"{folder}/{CHATBOTS_FILE}", _CHATBOTS_KEY, ChatbotFile, sync(folder))
        names = {element.name.lower() for element in own if element.name}
        not_own = lambda raw: str(raw.get("name", "")).strip().lower() in names  # noqa: E731
        shared = self._list(DefinitionKind.CHATBOT, GLOBAL_CHATBOTS_FILE, _CHATBOTS_KEY, ChatbotFile, sync(""), skip=not_own)
        return own + shared

    def _sync_chatbot(self, project_name: str, spec: ChatbotFile, prompt_folder: str) -> SyncOutcome:
        """The project's chatbot with this name (case-insensitive), else a new one."""
        prompt = spec.system_prompt
        if prompt is None:
            path = f"{prompt_folder}/{data_file_name(spec.system_prompt_file)}".lstrip("/")
            prompt = self._definitions.read_definition(path)
            if prompt is None or not prompt.strip():
                raise ValidationError(f"File del prompt non trovato o vuoto: {path}")
        values = dict(
            name=spec.name,
            kind=spec.kind,
            system_prompt=prompt.strip(),
            model=spec.model,
            description=spec.description.strip(),
            max_steps=spec.max_steps,
            tool_names=list(spec.tools),
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
        steps, edges = yaml_format.steps_and_edges(spec, current)
        values = dict(name=spec.name, description=spec.description, active=spec.active, steps=steps, edges=edges,
                      fields=spec.fields, purpose=spec.purpose)
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


def _shape(pipeline: Pipeline) -> tuple:
    """What a file defines of an automation: no ids, positions or prompt versions."""
    steps = [
        (
         step.name,
         step.kind,
         step.input_template,
         step.agent_config_name,
         step.tool_name,
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
    return pipeline.name, pipeline.description.strip(), pipeline.active, steps, edges, list(pipeline.fields), pipeline.purpose


def _load(text: str | None) -> dict | None:
    """A definition file's YAML; None when missing or empty."""
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


def _names(data: dict | None) -> dict[str, set[str]]:
    """The names in each list of a file, lowercase."""
    return {key: {str(item.get("name", "")).lower() for item in value if isinstance(item, dict)}
            for key, value in (data or {}).items() if isinstance(value, list)}


def _list_key(path: str) -> str:
    return _MERGED.get(path, "")


def _dump(data: dict) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=140)


def _first_error(exc: PydanticValidationError) -> str:
    """The first validation error as "field: message" (the file's names)."""
    error = exc.errors()[0]
    field = ".".join(str(part) for part in error["loc"])
    message = error["msg"].removeprefix("Value error, ")
    return f"{field}: {message}" if field else message
