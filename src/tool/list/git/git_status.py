"""git_status: changed files, branch and push/pull state of a repository of the
run's project. The project comes from the run; the model picks the repository."""
from datapizza.tools import Tool, tool

from core.error import AppError
from models.domain.tool import GitStatusResponse, ToolErrorResponse
from tool.context import ToolContext
from tool.list.git.errors import git_error
from tool.list.git.params import Repository
from tool.spec import ToolSpec


def build(context: ToolContext) -> Tool:

    @tool(name="git_status")
    def git_status(repository: Repository) -> GitStatusResponse | ToolErrorResponse:
        """Working-tree status of a git repository of the current project:
        branch, commits to push/pull against its upstream and the changed files
        (modified, added, deleted, renamed, untracked, conflicts; staged or not)."""
        try:
            status = context.git.status(context.require_project(), repository)
        except AppError as exc:
            return git_error(context, exc)

        return GitStatusResponse(
            repository=repository,
            clean=status.is_clean,
            status=status
        )

    return git_status


GIT_STATUS = ToolSpec(
    name="git_status",
    description="File modificati, branch e commit da pushare/pullare di un repository del progetto.",
    build=build,
)
