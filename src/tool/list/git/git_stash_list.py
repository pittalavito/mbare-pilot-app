"""git_stash_list: the stashes of a repository of the run's project, to pick
the one for git_stash_apply."""
from datapizza.tools import Tool, tool

from core.error import AppError
from models.domain.tool import GitStashListResponse, ToolErrorResponse
from tool.context import ToolContext
from tool.list.git.errors import git_error
from tool.list.git.params import Repository
from tool.spec import ToolSpec


def build(context: ToolContext) -> Tool:

    @tool(name="git_stash_list")
    def git_stash_list(repository: Repository) -> GitStashListResponse | ToolErrorResponse:
        """The stashes of a git repository of the current project (git stash
        list), newest first, with their message: the ref goes to git_stash_apply."""
        try:
            stashes = context.git.stash_list(context.require_project(), repository)
        except AppError as exc:
            return git_error(context, exc)
        return GitStashListResponse(repository=repository, stashes=stashes)

    return git_stash_list


GIT_STASH_LIST = ToolSpec(
    name="git_stash_list",
    description="Elenca gli stash di un repository del progetto (git stash list).",
    build=build,
)
