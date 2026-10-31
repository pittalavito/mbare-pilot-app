"""git_checkout: switch a repository of the run's project to an existing
branch (local, or only on the remote). Refused with uncommitted changes."""
from datapizza.tools import Tool, tool

from core.error import AppError
from models.domain.tool import GitCheckoutResponse, ToolErrorResponse
from tool.context import ToolContext
from tool.list.git.errors import git_error
from tool.list.git.params import Branch, Repository
from tool.spec import ToolSpec


def build(context: ToolContext) -> Tool:

    @tool(name="git_checkout")
    def git_checkout(repository: Repository, branch: Branch) -> GitCheckoutResponse | ToolErrorResponse:
        """Switch a git repository of the current project to an existing
        branch (git switch). A branch only on the remote becomes a local one
        tracking it. Refused if tracked files have uncommitted changes: use
        git_stash or git_commit first."""
        try:
            result = context.git.checkout(context.require_project(), repository, branch)
        except AppError as exc:
            return git_error(context, exc)
        return GitCheckoutResponse(repository=repository, **result.model_dump())

    return git_checkout


GIT_CHECKOUT = ToolSpec(
    name="git_checkout",
    description="Passa un repository del progetto a un branch esistente, locale o remoto; rifiuta con modifiche non committate.",
    build=build,
)
