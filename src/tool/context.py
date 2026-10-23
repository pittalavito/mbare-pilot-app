"""What a tool can use while an agent runs: the services and the project of the
run. Built by AgentService for every run; tools receive it through their
builder and never read the Container."""
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.error import ValidationError
from service.git_service import GitService

if TYPE_CHECKING:  # AgentService builds the ToolContext: imported only for the type
    from service.agent_service import AgentService


@dataclass(frozen=True)
class ToolContext:
    project_name: str | None
    """Project of the run; None for a run outside any project."""
    git: GitService
    agents: "AgentService | None" = None
    """For delegating to other agents (tool ask_agent); None = no delegation."""
    depth: int = 0
    """Delegation level of the run: 0 = asked by the user, 1 = asked by another agent."""

    def require_project(self) -> str:
        """The run's project; ValidationError for tools that need one."""
        if self.project_name is None:
            raise ValidationError("Questo tool funziona solo in un agente eseguito dentro un progetto.")
        return self.project_name
