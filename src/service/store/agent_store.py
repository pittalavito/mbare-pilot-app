"""The agents' library: roles, their versioned system prompts and the agent
configs (role + prompt + model + tools), global or of a project."""
from sqlalchemy.engine import Engine

from domain.store.db.agent_config_repository import DbAgentConfigRepository
from domain.store.db.agent_mapper import Adapter, Factory
from domain.store.db.prompt_repository import DbPromptRepository
from domain.store.db.role_repository import DbRoleRepository
from models.domain.agent import AgentConfig, AgentRole, SystemPrompt


class AgentStore:

    def __init__(self, engine: Engine):
        self._roles = DbRoleRepository(engine)
        self._prompts = DbPromptRepository(engine)
        self._configs = DbAgentConfigRepository(engine)

    # ----------------------------------------------------------------- roles
    def list_roles(self, project_name: str | None = None, include_global: bool = True) -> list[AgentRole]:
        """Global roles (``project_name`` None) or a project's, optionally with the global ones."""
        return [Adapter.to_role(row) for row in self._roles.list_scoped(project_name, include_global)]

    def get_role(self, name: str) -> AgentRole | None:
        row = self._roles.get(name)
        return Adapter.to_role(row) if row else None

    def save_role(self, role: AgentRole) -> AgentRole:
        return Adapter.to_role(self._roles.save(Factory.to_role_row(role)))

    def set_role_active(self, name: str, active: bool) -> AgentRole | None:
        """None when the role does not exist."""
        row = self._roles.get(name)
        if row is None:
            return None
        row.active = active
        return Adapter.to_role(self._roles.save(row))

    # --------------------------------------------------------------- prompts
    def list_prompts(self, role_name: str | None = None) -> list[SystemPrompt]:
        """Prompt versions, newest first."""
        return [Adapter.to_prompt(row) for row in self._prompts.list_versions(role_name)]

    def get_prompt(self, prompt_id: int) -> SystemPrompt | None:
        row = self._prompts.get(prompt_id)
        return Adapter.to_prompt(row) if row else None

    def create_prompt_version(self, role_name: str, text: str) -> SystemPrompt:
        return Adapter.to_prompt(self._prompts.create_version(role_name, text))

    def set_prompt_active(self, prompt_id: int, active: bool) -> SystemPrompt | None:
        """Toggle a version on/off (its text stays untouched). None when absent."""
        row = self._prompts.get(prompt_id)
        if row is None:
            return None
        row.active = active
        return Adapter.to_prompt(self._prompts.save(row))

    # --------------------------------------------------------- agent configs
    def list_configs(self, project_name: str | None = None, include_global: bool = True) -> list[AgentConfig]:
        """Global configs (``project_name`` None) or a project's, optionally with the global ones."""
        return [Adapter.to_agent_config(row) for row in self._configs.list_scoped(project_name, include_global)]

    def get_config(self, name: str) -> AgentConfig | None:
        row = self._configs.get(name)
        return Adapter.to_agent_config(row) if row else None

    def save_config(self, config: AgentConfig) -> AgentConfig:
        return Adapter.to_agent_config(self._configs.save(Factory.to_agent_config_row(config)))

    def delete_config(self, name: str) -> bool:
        return self._configs.delete(name)
