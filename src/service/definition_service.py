"""Definitions as files (models/domain/definitions.py): agents, chatbots and
automations written as YAML under ``<MBARE_PILOT_HOME>/definition/``, applied
to a project on request:

- ``global-agent.yml``: agents of the Library (global);
- ``project/<slug>/agent.yml``: the project's agents;
- ``project/<slug>/chat-bot.yml``: the project's chatbot, else ``global-chat-bot.yml``;
- ``project/<slug>/automation.yml``: the project's automations, plus those of
  ``global-automation.yml`` with a name the project does not use.

``sync(project)`` validates every element with the same rules as the API (the
same services do the work) and creates or updates it, matched by name: the
file wins over changes made from the UI. What is not in the files is left as it
is. An element with errors is skipped and reported; the others are applied.
An empty file (or one with only comments) defines nothing."""
from collections.abc import Callable
from typing import Any

import yaml
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from core.error import AppError, NotFoundError, ValidationError
from core.observability import LogPrefix, observed
from domain.pipeline.graph import linear_edges
from domain.project.data_paths import AGENTS_FILE, AUTOMATIONS_FILE, CHATBOT_FILE, GLOBAL_AGENTS_FILE, GLOBAL_AUTOMATIONS_FILE, GLOBAL_CHATBOT_FILE, data_file_name, project_definitions
from models.domain.agent import AgentConfig, AgentRole
from models.domain.definitions import AgentFile, AutomationFile, ChatbotFile, DefinitionKind, StepFile, SyncItem, SyncOutcome, SyncReport
from models.domain.pipeline import Pipeline, PipelineEdge, PipelineStep, StepAgent, StepKind
from service.agent_config_service import AgentConfigService
from service.chatbot_service import ChatbotService
from service.pipeline_service import PipelineService
from service.store_service import StoreService

_AGENTS_KEY = "agents"
_AUTOMATIONS_KEY = "automations"


class DefinitionService:

    def __init__(self, store_service: StoreService, agent_config_service: AgentConfigService, chatbot_service: ChatbotService, pipeline_service: PipelineService):
        self._store = store_service
        self._agents = agent_config_service
        self._chatbots = chatbot_service
        self._pipelines = pipeline_service

    @observed(LogPrefix.DEFINITION_SERVICE)
    def sync(self, project_name: str) -> SyncReport:
        """Global agents, the project's agents, its chatbot, its automations."""
        if self._store.get_project(project_name) is None:
            raise NotFoundError(f"Progetto non trovato: {project_name}")
        folder = project_definitions(project_name)
        items = self._list(DefinitionKind.AGENT, GLOBAL_AGENTS_FILE, _AGENTS_KEY, AgentFile, lambda spec: self._sync_agent(None, spec))
        items += self._list(DefinitionKind.AGENT, f"{folder}/{AGENTS_FILE}", _AGENTS_KEY, AgentFile, lambda spec: self._sync_agent(project_name, spec))
        items += self._chatbot(project_name, folder)
        items += self._automations(project_name, folder)
        return SyncReport(project_name=project_name, items=items)

    # ---------------------------------------------------------------- files
    def _list(self, kind: DefinitionKind, path: str, key: str, schema: type[BaseModel], sync: Callable[[Any], SyncOutcome], skip: Callable[[dict], bool] = lambda raw: False) -> list[SyncItem]:
        """One item per element of the file's ``key`` list (``skip`` leaves some out)."""
        try:
            raw = self._read(path)
            if raw is None:
                return []
            elements = raw.get(key)
            if not isinstance(elements, list):
                raise ValidationError(f"il file deve avere la lista «{key}:».")
        except AppError as exc:
            return [SyncItem(kind=kind, file=path, outcome=SyncOutcome.ERROR, message=str(exc))]
        return [
            _apply(kind, path, element, index, schema, sync)
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
        role = self._store.get_role(spec.role)
        if role is None:
            self._agents.save_role(AgentRole(name=spec.role, project_name=project_name), create=True)
        elif role.project_name != project_name:
            raise ValidationError(f"Il ruolo {spec.role} esiste già ma non è {scope}: usa un altro nome.")
        existing = self._store.get_agent_config(spec.name)
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
    def _chatbot(self, project_name: str, folder: str) -> list[SyncItem]:
        """The project's chat-bot.yml, else the global one (a base for every project)."""
        for path, prompt_folder in ((f"{folder}/{CHATBOT_FILE}", folder), (GLOBAL_CHATBOT_FILE, "")):
            try:
                raw = self._read(path)
            except AppError as exc:
                return [SyncItem(kind=DefinitionKind.CHATBOT, file=path, outcome=SyncOutcome.ERROR, message=str(exc))]
            if raw is not None:
                return [_apply(DefinitionKind.CHATBOT, path, raw, None, ChatbotFile, lambda spec: self._sync_chatbot(project_name, spec, prompt_folder))]
        return []

    def _sync_chatbot(self, project_name: str, spec: ChatbotFile, prompt_folder: str) -> SyncOutcome:
        """The project's chatbot: the one with this name, else the existing one
        (one per project: it gets this name), else a new one."""
        prompt = spec.system_prompt
        if prompt is None:
            path = f"{prompt_folder}/{data_file_name(spec.system_prompt_file)}".lstrip("/")
            prompt = self._store.read_definition(path)
            if prompt is None or not prompt.strip():
                raise ValidationError(f"File del prompt non trovato o vuoto: {path}")
        values = dict(
            name=spec.name, 
            system_prompt=prompt.strip(), 
            model=spec.model, 
            description=spec.description.strip(),
            max_steps=spec.max_steps, 
            tool_names=spec.tools
        )
        chatbots = self._chatbots.list_chatbots(project_name)
        current = next((bot for bot in chatbots if bot.name.lower() == spec.name.lower()), chatbots[0] if chatbots else None)
        if current is None:
            self._chatbots.create_chatbot(project_name, **values)
            return SyncOutcome.CREATED
        if {key: getattr(current, key) for key in values} == values:
            return SyncOutcome.UNCHANGED
        self._chatbots.update_chatbot(current.id, **values)
        return SyncOutcome.UPDATED

    # ---------------------------------------------------------- automations
    def _automations(self, project_name: str, folder: str) -> list[SyncItem]:
        """The project's automations, then the global ones it does not redefine (by name)."""
        sync = lambda spec: self._sync_automation(project_name, spec)  # noqa: E731
        path = f"{folder}/{AUTOMATIONS_FILE}"
        items = self._list(DefinitionKind.AUTOMATION, path, _AUTOMATIONS_KEY, AutomationFile, sync)
        try:
            own = {str(element.get("name", "")).strip().lower()
                   for element in (self._read(path) or {}).get(_AUTOMATIONS_KEY) or [] if isinstance(element, dict)}
        except AppError:
            own = set()
        return items + self._list(DefinitionKind.AUTOMATION, GLOBAL_AUTOMATIONS_FILE, _AUTOMATIONS_KEY, AutomationFile, sync, skip=lambda raw: str(raw.get("name", "")).strip().lower() in own)

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


def _apply(kind: DefinitionKind, path: str, raw: Any, index: int | None, schema: type[BaseModel], sync: Callable[[Any], SyncOutcome]) -> SyncItem:
    """Validate and apply one element; its errors become the item's message."""
    label = raw.get("name") if isinstance(raw, dict) and raw.get("name") else (f"elemento {index}" if index else None)
    try:
        if not isinstance(raw, dict):
            raise ValidationError("ogni elemento deve contenere dei campi (nome: valore).")
        spec = schema.model_validate(raw)
        outcome = sync(spec)
    except PydanticValidationError as exc:
        return SyncItem(kind=kind, file=path, name=label, outcome=SyncOutcome.ERROR, message=_first_error(exc))
    except AppError as exc:
        return SyncItem(kind=kind, file=path, name=label, outcome=SyncOutcome.ERROR, message=str(exc))
    return SyncItem(kind=kind, file=path, name=spec.name, outcome=outcome)


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
