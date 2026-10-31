"""git_pull_all_by_branch: bring every repository of the run's project to a
branch and update it from the remote (fetch, switch, pull --ff-only).
Repositories with local changes or without the branch are skipped, never forced."""
from datapizza.tools import Tool, tool

from core.error import AppError
from models.domain.tool import GitPullAllResponse, ToolErrorResponse
from tool.context import ToolContext
from tool.list.git.errors import git_error, hide_local_paths
from tool.list.git.params import Branch
from tool.spec import ToolSpec


def build(context: ToolContext) -> Tool:

    @tool(name="git_pull_all_by_branch")
    def git_pull_all_by_branch(branch: Branch) -> GitPullAllResponse | ToolErrorResponse:
        """For every git repository of the current project: fetch, switch to
        the branch (if it exists locally or on the remote) and pull it in
        fast-forward. Repositories with uncommitted changes to tracked files,
        without the branch or that cannot fast-forward are skipped with the
        reason. Returns one outcome per repository."""
        try:
            outcomes = context.git.pull_all_by_branch(context.require_project(), branch)
        except AppError as exc:
            return git_error(context, exc)
        for outcome in outcomes:
            outcome.reason = hide_local_paths(context, outcome.reason)
        return GitPullAllResponse(branch=branch.strip(), repositories=outcomes)

    return git_pull_all_by_branch


GIT_PULL_ALL_BY_BRANCH = ToolSpec(
    name="git_pull_all_by_branch",
    description="Porta tutti i repository del progetto su un branch e li aggiorna in fast-forward; salta quelli con modifiche locali.",
    build=build,
)
