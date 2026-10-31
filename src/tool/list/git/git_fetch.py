"""git_fetch: download the remotes' news for a repository of the run's project
(git fetch --all --prune) without touching branches or files."""
from datapizza.tools import Tool, tool

from core.error import AppError
from models.domain.tool import GitFetchResponse, ToolErrorResponse
from tool.context import ToolContext
from tool.list.git.errors import git_error
from tool.list.git.params import Repository
from tool.spec import ToolSpec


def build(context: ToolContext) -> Tool:

    @tool(name="git_fetch")
    def git_fetch(repository: Repository) -> GitFetchResponse | ToolErrorResponse:
        """Fetch every remote of a git repository of the current project (git
        fetch --all --prune): changes no branch nor file. Returns how many
        commits the current branch now has to push and to pull."""
        try:
            result = context.git.fetch(context.require_project(), repository)
        except AppError as exc:
            return git_error(context, exc)
        return GitFetchResponse(repository=repository, **result.model_dump())

    return git_fetch


GIT_FETCH = ToolSpec(
    name="git_fetch",
    description="Scarica le novità dai remoti di un repository del progetto (git fetch --all --prune), senza toccare branch e file.",
    build=build,
)
