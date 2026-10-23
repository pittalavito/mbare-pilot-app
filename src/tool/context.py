"""What a tool can use while an agent runs: the services and the project of the
run. Built by AgentService for every run; tools receive it through their
builder and never read the Container."""
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.error import ValidationError
from models.domain.agent import RunOrigin
from service.git_service import GitService

if TYPE_CHECKING:  # AgentService builds the ToolContext: imported only for the type
    from service.agent_service import AgentService
    from service.masking_service import MaskSession
    from service.pipeline_service import PipelineService


@dataclass(frozen=True)
class ToolContext:
    project_name: str | None
    """Project of the run; None for a run outside any project."""
    git: GitService
    agents: "AgentService | None" = None
    """For delegating to other agents (tool ask_agent); None = no delegation."""
    depth: int = 0
    """Delegation level of the run: 0 = asked by the user, 1 = asked by another agent."""
    pipelines: "PipelineService | None" = None
    """For starting the project's automations (tool run_automation); None = not possible."""
    origin: RunOrigin = RunOrigin.MANUAL
    """What triggered the run (a run inside an automation cannot start automations)."""
    mask: "MaskSession | None" = None
    """The run's masking (runs of a project): tools register sensitive values here."""

    def register_sensitive(self, category, value: str) -> None:
        """A sensitive value the tool read (e.g. a repository name): masked from now on."""
        if self.mask is not None and value:
            self.mask.register(category, value)

    def require_project(self) -> str:
        """The run's project; ValidationError for tools that need one."""
        if self.project_name is None:
            raise ValidationError("Questo tool funziona solo in un agente eseguito dentro un progetto.")
        return self.project_name
