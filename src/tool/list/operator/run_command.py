"""run_command (the Operator, plan 11): runs one of the project's allowed
commands in a repository of the project (e.g. ``mvn -B clean install``). A
command outside the list is not run: the user is asked in the agent panel and
the agent must stop and wait. A failing command (exit code not 0) comes back
as an error with the last lines of its output."""
from typing import Annotated

from datapizza.tools import Tool, tool

from core.error import AppError
from models.domain.tool import CommandRunResponse, ToolErrorResponse
from tool.context import ToolContext
from tool.list.git.errors import git_error, hide_local_paths
from tool.list.git.params import Repository
from tool.spec import ToolSpec

Command = Annotated[str, "The command line, exactly as allowed in the project, e.g. 'mvn -B clean install'."]

NOT_ALLOWED = ("Comando non permesso in questo progetto: ho chiesto il permesso all'utente nel pannello. "
               "Fermati qui e digli che serve il suo ok per «{command}»; riprova solo quando te lo dice.")


def build(context: ToolContext) -> Tool:

    @tool(name="run_command")
    def run_command(repository: Repository, command: Command) -> CommandRunResponse | ToolErrorResponse:
        """Run a command in a git repository of the current project (no shell):
        only the commands the project allows (build, install, tests). Returns
        the exit code and the last lines of the output. If it is not allowed the
        user is asked: stop and wait for their ok."""
        try:
            outcome = context.require_commands().run(context.require_project(), repository, command)
        except AppError as exc:
            return git_error(context, exc)
        if not outcome.allowed:
            return ToolErrorResponse(error=NOT_ALLOWED.format(command=" ".join(command.split())))
        output = hide_local_paths(context, outcome.output)
        if outcome.exit_code != 0:
            return ToolErrorResponse(error=f"«{command}» è uscito con codice {outcome.exit_code}:\n{output}")
        return CommandRunResponse(repository=repository, command=command, exit_code=0, output=output)

    return run_command


RUN_COMMAND = ToolSpec(
    name="run_command",
    description="Lancia in un repository del progetto uno dei comandi permessi (build, install, test); gli altri li chiede all'utente.",
    build=build,
)
