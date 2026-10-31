"""The agents' library: roles (``agent_role``), system prompt versions
(``system_prompt``) and agent configs (``agent_config``), domain <-> rows."""
from domain.store.db.mapper import as_utc
from models.domain.agent import AgentConfig, AgentRole, SystemPrompt
from models.store.db import AgentConfigTable, AgentRoleTable, SystemPromptTable


class Adapter:
    """Read seam: DB rows -> domain models."""

    @staticmethod
    def to_role(row: AgentRoleTable) -> AgentRole:
        return AgentRole.model_validate(row.model_dump())

    @staticmethod
    def to_prompt(row: SystemPromptTable) -> SystemPrompt:
        prompt = SystemPrompt.model_validate(row.model_dump())
        prompt.created_at = as_utc(prompt.created_at)
        return prompt

    @staticmethod
    def to_agent_config(row: AgentConfigTable) -> AgentConfig:
        return AgentConfig(
            name=row.name,
            project_name=row.project_name,
            description=row.description,
            role_name=row.role_name,
            prompt_id=row.prompt_id,
            model=row.model,
            max_steps=row.max_steps,
            tool_names=list(row.tool_names),
        )


class Factory:
    """Write seam: domain models -> DB rows."""

    @staticmethod
    def to_role_row(role: AgentRole) -> AgentRoleTable:
        return AgentRoleTable(**role.model_dump())

    @staticmethod
    def to_agent_config_row(config: AgentConfig) -> AgentConfigTable:
        return AgentConfigTable(
            name=config.name,
            project_name=config.project_name,
            description=config.description,
            role_name=config.role_name,
            prompt_id=config.prompt_id,
            model=config.model,
            max_steps=config.max_steps,
            tool_names=list(config.tool_names),
        )
