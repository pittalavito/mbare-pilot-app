"""Default roles, prompts and configurations, seeded into the DB at startup.
Seeding only inserts what is missing: anything edited in the DB wins."""
from pydantic import BaseModel

from models.domain.agent import AgentRole
from models.domain.chat import ModelKey


class ConfigSeed(BaseModel):
    """A default configuration; it uses the latest prompt version of its role."""
    name: str
    description: str = ""
    role_name: str
    model: ModelKey
    max_steps: int = 4
    tool_names: list[str] = []


DEFAULT_ROLES: list[AgentRole] = [
    AgentRole(name="hello", description="Assistente di esempio che saluta e conta parole."),
]

DEFAULT_PROMPTS: dict[str, str] = {
    "hello": "Sei un assistente. Usa i tool a disposizione quando servono.",
}
"""First prompt version per role (created only when the role has no prompt yet)."""

DEFAULT_CONFIGS: list[ConfigSeed] = [
    ConfigSeed(
        name="hello",
        description="Agente di esempio con i tool hello_world",
        role_name="hello",
        model="openai/gpt-4o",
        max_steps=4,
        tool_names=["hello_world"],
    ),
]
