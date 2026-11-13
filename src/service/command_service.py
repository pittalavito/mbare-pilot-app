"""The commands the Operator may run (plan 11), per project: an allowed list
written in Progetto → Impostazioni (the detected install and test commands are
offered), and nothing else. A command outside the list is not run: it becomes
a request the user answers in the agent panel, «Sempre» (added to the list)
or «Solo stavolta» (a grant used up by the next run of that command).

``run`` executes in a repository of the project, without a shell, and gives
back only the exit code and the last lines of the output (few tokens)."""
import os
import shutil
from dataclasses import dataclass

from core.error import NotFoundError, ValidationError
from domain.client.command.client import CommandClient
from domain.dev import tests
from models.domain.project import CommandRequest, Project
from service.git_service import GitService
from service.store.project_store import ProjectStore

TIMEOUT_SECONDS = 30 * 60
TAIL_LINES = 30
"""How much of a command's output reaches the agent: its last lines."""
_TAIL_CHARS = 3000


def normalize(command: str) -> str:
    """The command as compared with the list: single spaces, no ends."""
    return " ".join(command.split())


@dataclass(frozen=True)
class CommandOutcome:
    allowed: bool
    """False: not run, a request is waiting for the user."""
    exit_code: int | None = None
    output: str = ""
    """The last lines of stdout and stderr."""

    @property
    def ok(self) -> bool:
        return self.allowed and self.exit_code == 0


class CommandService:

    def __init__(self, projects: ProjectStore, git: GitService, client: CommandClient | None = None):
        self._projects = projects
        self._git = git
        self._client = client or CommandClient()

    # ---------------------------------------------------------------- list
    def allowed(self, project_name: str) -> list[str]:
        return list(self._project(project_name).allowed_commands)

    def suggested(self, project_name: str) -> list[str]:
        """The detected install and test commands of the project's repositories not in the list yet."""
        project = self._project(project_name)
        allowed = set(project.allowed_commands)
        found: list[str] = []
        for repository in self._git.repositories(project_name):
            root = self._git.repository_folder(project_name, repository.path)
            files = {path.name for path in root.iterdir()}
            kind = tests.detect(files)
            written = project.test_commands.get(repository.path, "")
            for command in (tests.install_command(kind, files), written or tests.default_command(kind, files)):
                if command and command not in allowed and command not in found:
                    found.append(command)
        return found

    def save_allowed(self, project_name: str, commands: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(normalize(command) for command in commands if normalize(command)))
        project = self._project(project_name)
        requests = [request for request in project.command_requests if request.command not in cleaned]
        self._save(project, allowed_commands=cleaned, command_requests=requests)
        return cleaned

    # ------------------------------------------------------------ requests
    def requests(self, project_name: str) -> list[CommandRequest]:
        return list(self._project(project_name).command_requests)

    def answer(self, project_name: str, command: str, *, allow: bool, always: bool = False) -> None:
        """The user's answer to a request: «Sempre» (``always``) adds it to the list,
        «Solo stavolta» grants one run, «No» (``allow`` False) drops it."""
        command = normalize(command)
        project = self._project(project_name)
        requests = [request for request in project.command_requests if request.command != command]
        if len(requests) == len(project.command_requests):
            raise NotFoundError(f"Nessuna richiesta per il comando: {command}")
        allowed, grants = list(project.allowed_commands), list(project.command_grants)
        if allow and always:
            allowed.append(command)
        elif allow:
            grants.append(command)
        self._save(project, allowed_commands=list(dict.fromkeys(allowed)), command_requests=requests, command_grants=grants)

    # ----------------------------------------------------------------- run
    def run(self, project_name: str, repository: str, command: str) -> CommandOutcome:
        """Runs an allowed (or granted once) command in ``repository``; else
        records the request and returns ``allowed=False`` without running it."""
        command = normalize(command)
        if not command:
            raise ValidationError("Scrivi il comando da eseguire.")
        project = self._project(project_name)
        folder = self._git.repository_folder(project_name, repository)  # inside the project, or ValidationError
        if command not in project.allowed_commands:
            if command not in project.command_grants:
                if all(request.command != command for request in project.command_requests):
                    request = CommandRequest(repository=repository.strip().strip("/\\"), command=command)
                    self._save(project, command_requests=[*project.command_requests, request])
                return CommandOutcome(allowed=False)
            grants = list(project.command_grants)
            grants.remove(command)
            self._save(project, command_grants=grants)
        arguments = tests.split(command)
        executable = shutil.which(arguments[0], path=os.environ.get("PATH")) if not os.path.dirname(arguments[0]) else None
        result = self._client.run(folder, [executable or arguments[0], *arguments[1:]], TIMEOUT_SECONDS)
        return CommandOutcome(allowed=True, exit_code=result.returncode, output=_tail(result.output))

    # ------------------------------------------------------------- helpers
    def _project(self, project_name: str) -> Project:
        project = self._projects.get(project_name)
        if project is None:
            raise NotFoundError(f"Progetto non trovato: {project_name}")
        return project

    def _save(self, project: Project, **changes) -> None:
        self._projects.save(project.model_copy(update=changes))


def _tail(output: str) -> str:
    lines = [line.rstrip() for line in output.splitlines() if line.strip()]
    text = "\n".join(lines[-TAIL_LINES:])
    return text[-_TAIL_CHARS:]
