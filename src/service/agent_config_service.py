"""Agent definitions: roles, versioned system prompts, the tool catalog and the
runnable configurations. Validates every write against the rest (role exists,
prompt belongs to the role, tools are catalogued and implemented) and resolves
a configuration into an ``AgentSpec`` for AgentService.

Scope: roles and configs are global (``project_name`` None, usable by every
project) or owned by one project. A project config may use a global role or
one of its own; a global config only global roles. Prompts follow their role.
Names are unique across all scopes."""
from core.error import ConflictError, NotFoundError, ValidationError
from models.domain.agent import AgentConfig, AgentRole, AgentSpec, SystemPrompt, ToolInfo
from service.model_service import require_usable_model
from service.store.agent_store import AgentStore
from service.store.catalog_store import CatalogStore
from service.store_service import StoreService
from tool.registry import TOOL_REGISTRY


class AgentConfigService:

    def __init__(self, store_service: StoreService, agents: AgentStore, catalog: CatalogStore):
        self._store = store_service
        self._agents = agents
        self._catalog = catalog

    # ----------------------------------------------------------------- tools
    def sync_tools(self) -> None:
        """Register every tool implemented in code into the DB catalog."""
        self._catalog.sync_tools([ToolInfo(name=spec.name, description=spec.description) for spec in TOOL_REGISTRY.values()])

    def list_tools(self) -> list[ToolInfo]:
        """The catalog, with ``chatbot_only`` from the code."""
        return [
            tool.model_copy(update={"chatbot_only": tool.name in TOOL_REGISTRY and TOOL_REGISTRY[tool.name].chatbot_only})
            for tool in self._catalog.list_tools(implemented=set(TOOL_REGISTRY))
        ]

    # ----------------------------------------------------------------- roles
    def list_roles(self, project_name: str | None = None, include_global: bool = True) -> list[AgentRole]:
        """Global roles, or a project's (with the global ones unless ``include_global=False``)."""
        return self._agents.list_roles(project_name, include_global)

    def get_role(self, name: str) -> AgentRole:
        role = self._agents.get_role(name)
        if role is None:
            raise NotFoundError(f"Ruolo non trovato: {name}")
        return role

    def save_role(self, role: AgentRole, *, create: bool = False) -> AgentRole:
        """Persist ``role``. Its scope is fixed at creation: updates keep it."""
        existing = self._agents.get_role(role.name)
        if existing is not None:
            if create:
                raise ConflictError(f"Esiste già un ruolo chiamato {role.name}.")
            role = role.model_copy(update={"project_name": existing.project_name})
        else:
            self._require_project(role.project_name)
        return self._agents.save_role(role)

    def set_role_active(self, name: str, active: bool) -> AgentRole:
        role = self._agents.set_role_active(name, active)
        if role is None:
            raise NotFoundError(f"Ruolo non trovato: {name}")
        return role

    # --------------------------------------------------------------- prompts
    def list_prompts(self, role_name: str | None = None) -> list[SystemPrompt]:
        """Prompt versions, newest first."""
        return self._agents.list_prompts(role_name)

    def create_prompt_version(self, role_name: str, text: str) -> SystemPrompt:
        """New version of the role's prompt. Returns the latest version
        unchanged when ``text`` is identical to it (no duplicate versions)."""
        self._require_role(role_name)
        text = text.strip()
        if not text:
            raise ValidationError("Il system prompt non può essere vuoto.")
        latest = self.latest_prompt(role_name)
        if latest is not None and latest.text == text:
            return latest
        return self._agents.create_prompt_version(role_name, text)

    def latest_prompt(self, role_name: str) -> SystemPrompt | None:
        versions = self._agents.list_prompts(role_name)
        return versions[0] if versions else None

    def latest_active_prompt(self, role_name: str) -> SystemPrompt | None:
        return next((prompt for prompt in self._agents.list_prompts(role_name) if prompt.active), None)

    def set_prompt_active(self, prompt_id: int, active: bool) -> SystemPrompt:
        prompt = self._agents.set_prompt_active(prompt_id, active)
        if prompt is None:
            raise NotFoundError(f"Prompt non trovato: {prompt_id}")
        return prompt

    # --------------------------------------------------------------- configs
    def list_configs(self, project_name: str | None = None, include_global: bool = True) -> list[AgentConfig]:
        """Global configs, or a project's (with the global ones unless ``include_global=False``)."""
        return self._agents.list_configs(project_name, include_global)

    def get_config(self, name: str) -> AgentConfig:
        config = self._agents.get_config(name)
        if config is None:
            raise NotFoundError(f"Configurazione agente non trovata: {name}")
        return config

    def save_config(self, config: AgentConfig, *, create: bool = False) -> AgentConfig:
        """Validate and persist ``config``. With ``create=True`` an existing
        name is a ConflictError instead of being overwritten."""
        existing = self._agents.get_config(config.name)
        if existing is not None and create:
            raise ConflictError(f"Esiste già un agente chiamato {config.name}.")
        if existing is not None and existing.project_name != config.project_name:
            raise ValidationError("Lo scope di un agente (globale o di progetto) non si può cambiare.")
        self._require_project(config.project_name)
        role = self._require_role(config.role_name)
        if role.project_name not in (None, config.project_name):
            raise ValidationError(f"Il ruolo {role.name} appartiene al progetto {role.project_name}.")
        prompt = self._agents.get_prompt(config.prompt_id)
        if prompt is None or prompt.role_name != config.role_name:
            raise ValidationError(f"Il prompt scelto non appartiene al ruolo {config.role_name}.")
        self._require_active(role, prompt)
        require_usable_model(self._catalog, config.model)
        usable = {tool.name for tool in self.list_tools() if tool.available}
        unusable = [name for name in config.tool_names if name not in usable]
        if unusable:
            raise ValidationError(f"Tool non disponibili: {', '.join(unusable)}")
        return self._agents.save_config(config)

    def delete_config(self, name: str) -> bool:
        return self._agents.delete_config(name)

    def resolve(self, name: str) -> AgentSpec:
        """The configuration plus its pinned prompt version. Raises
        ValidationError when its role or prompt version is inactive."""
        config = self.get_config(name)
        prompt = self._agents.get_prompt(config.prompt_id)
        if prompt is None:
            raise NotFoundError(f"Prompt {config.prompt_id} della configurazione {name} non trovato.")
        self._require_active(self._require_role(config.role_name), prompt)
        return AgentSpec(config=config, prompt=prompt)

    def blocked_reason(self, config: AgentConfig) -> str | None:
        """Why ``config`` cannot run right now, or None when it can."""
        try:
            self.resolve(config.name)
        except (NotFoundError, ValidationError) as exc:
            return str(exc)
        return None

    # ----------------------------------------------------------------- seeds
    def _require_project(self, project_name: str | None) -> None:
        if project_name is not None and self._store.get_project(project_name) is None:
            raise ValidationError(f"Progetto inesistente: {project_name}")

    def _require_role(self, role_name: str) -> AgentRole:
        role = self._agents.get_role(role_name)
        if role is None:
            raise ValidationError(f"Ruolo inesistente: {role_name}")
        return role

    @staticmethod
    def _require_active(role: AgentRole, prompt: SystemPrompt) -> None:
        if not role.active:
            raise ValidationError(f"Il ruolo {role.name} è disattivato.")
        if not prompt.active:
            raise ValidationError(f"La versione v{prompt.version} del prompt di {role.name} è disattivata.")
