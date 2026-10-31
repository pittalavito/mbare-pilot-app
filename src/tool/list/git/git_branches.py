"""git_branches: local and remote branches of a repository of the run's project."""
from datapizza.tools import Tool, tool

from core.error import AppError
from models.domain.tool import GitBranchesResponse, ToolErrorResponse
from tool.context import ToolContext
from tool.list.git.errors import git_error
from tool.list.git.params import Repository
from tool.spec import ToolSpec


def build(context: ToolContext) -> Tool:

    @tool(name="git_branches")
    def git_branches(repository: Repository) -> GitBranchesResponse | ToolErrorResponse:
        """Branches of a git repository of the current project: the current
        one, the local ones (upstream, commits to push/pull, latest commit,
        upstream deleted on the remote) and the remote ones as of the last fetch."""
        try:
            result = context.git.branches(context.require_project(), repository)
        except AppError as exc:
            return git_error(context, exc)
        return GitBranchesResponse(repository=repository, current=result.current, local=result.local, remote=result.remote)

    return git_branches


GIT_BRANCHES = ToolSpec(
    name="git_branches",
    description="Branch locali e remoti di un repository del progetto, con quello corrente e i commit da pushare/pullare.",
    build=build,
)
