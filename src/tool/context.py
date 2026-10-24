"""What a tool can use while an agent runs: the services and the project of the
run. Built by AgentService for every run; tools receive it through their
builder and never read the Container."""
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.error import ValidationError
from models.domain.agent import RunOrigin
from service.git_service import GitService

if TYPE_CHECKING:  # services imported only for the type
    from service.masking_service import MaskSession
    from service.pipeline_service import PipelineService
    from service.project_data_service import ProjectDataService


@dataclass(frozen=True)
class ToolContext:
    project_name: str | None
    """Project of the run; None for a run outside any project."""
    git: GitService
    pipelines: "PipelineService | None" = None
    """For the project's automations (tools run_automation, automation_status); None = not possible."""
    origin: RunOrigin = RunOrigin.MANUAL
    """What triggered the run (the automation tools work only in a chatbot's run)."""
    project_data: "ProjectDataService | None" = None
    """For reading the project's context files (tool read_context); None = not possible."""
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
