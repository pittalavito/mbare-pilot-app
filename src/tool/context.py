"""What a tool can use while an agent runs: the services and the project of the
run. Built by AgentService for every run; tools receive it through their
builder and never read the Container. Masking is not here: the agent layer
(domain/agent/masking.py) handles it around the tools."""
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.error import ValidationError
from models.domain.agent import RunOrigin
from service.git_service import GitService

if TYPE_CHECKING:  # services imported only for the type
    from service.code_todo_service import CodeTodoService
    from service.command_service import CommandService
    from service.copilot_service import CopilotService
    from service.pipeline_service import PipelineService
    from service.project_data_service import ProjectDataService
    from service.rag_service import RagService


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
    code_todos: "CodeTodoService | None" = None
    """For the todoMbarePilot comments of the code (tool create_code_reference); None = not possible."""
    rag: "RagService | None" = None
    """For searching the project's context index (tool search_context); None = not possible."""
    open_note: str | None = None
    """The note open next to the chat (the Refiner's tools work only on it); None = none."""
    commands: "CommandService | None" = None
    """For the project's allowed commands (tool run_command); None = not possible."""

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

    def require_code_todos(self) -> "CodeTodoService":
        """The code comments' service; ValidationError when the run has none."""
        return _required(self.code_todos, "commenti del codice")

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
