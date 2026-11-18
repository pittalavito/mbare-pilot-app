"""What a tool can use while an agent runs: the services and the project of the
run. Built by AgentService for every run; tools receive it through their
builder and never read the Container. Masking is not here: the agent layer
(domain/agent/masking.py) handles it around the tools."""
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from core.error import ValidationError
from domain.client.command.client import CommandClient
from models.domain.agent import RunOrigin
from service.git_service import GitService

if TYPE_CHECKING:  # services imported only for the type
    from service.code_search_service import CodeSearchService
    from service.command_service import CommandService
    from service.copilot_service import CopilotService
    from service.maven_service import MavenService
    from service.pipeline_service import PipelineService
    from service.project_data_service import ProjectDataService
    from service.rag_service import RagService
    from service.tool_request_service import ToolRequestService


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
    """For the project's notes (agent tasks, activities, references); None = not possible."""
    copilot: "CopilotService | None" = None
    """For delegating agent tasks to Copilot (tools delegate_task, copilot_status); None = not possible."""
    code_search: "CodeSearchService | None" = None
    """For the free search in the code (tools search_code, save_code_search); None = not possible."""
    rag: "RagService | None" = None
    """For searching the project's context index (tool search_context); None = not possible."""
    open_note: str | None = None
    """The note open next to the chat (the Refiner's tools work only on it); None = none."""
    commands: "CommandService | None" = None
    """For the project's allowed commands (tool run_command); None = not possible."""
    tool_requests: "ToolRequestService | None" = None
    """For the Architetto's requests of tools (tool request_tool); None = not possible."""
    command_client: CommandClient = field(default_factory=CommandClient)
    """Runs the tests' command (tool run_tests)."""

    @property
    def maven(self) -> "MavenService":
        """The POMs of the project's repositories (stateless, built on ``git``)."""
        from service.maven_service import MavenService
        return MavenService(self.git)

    def require_project(self) -> str:
        """The run's project; ValidationError for tools that need one."""
        if self.project_name is None:
            raise ValidationError("Questo tool funziona solo in un agente eseguito dentro un progetto.")
        return self.project_name

    def require_pipelines(self) -> "PipelineService":
        """The automations' service; ValidationError when the run has none."""
        return _required(self.pipelines, "automation")

    def require_project_data(self) -> "ProjectDataService":
        """The project data's service; ValidationError when the run has none."""
        return _required(self.project_data, "dati del progetto")

    def require_code_search(self) -> "CodeSearchService":
        """The code search's service; ValidationError when the run has none."""
        return _required(self.code_search, "ricerca nel codice")

    def require_rag(self) -> "RagService":
        """The context index's service; ValidationError when the run has none."""
        return _required(self.rag, "contesto del progetto")

    def require_commands(self) -> "CommandService":
        """The allowed commands' service; ValidationError when the run has none."""
        return _required(self.commands, "comandi del progetto")

    def require_copilot(self) -> "CopilotService":
        """The Copilot service; ValidationError when the run has none."""
        return _required(self.copilot, "Copilot")


def _required[ServiceT](service: ServiceT | None, what: str) -> ServiceT:
    if service is None:
        raise ValidationError(f"Questo tool non ha accesso a {what} in questa run.")
    return service
