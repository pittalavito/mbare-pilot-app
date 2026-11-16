"""git_pull_by_branch: one repository of the run's project on a branch,
updated from the remote (fetch, switch, pull --ff-only): the same steps and
reasons to skip as git_pull_all_by_branch; it fails on an error, not on a skip."""
from pydantic import BaseModel, Field

from core.error import UpstreamError, ValidationError
from models.domain.git import GitBranchPullOutcome, GitBulkStatus
from tool.context import ToolContext
from tool.list.git.git_pull_all_by_branch import outcome_line
from tool.spec import params_tool


class Params(BaseModel):
    repository: str = Field(..., description="Repository folder in the project ('' = the project folder).")
    branch: str = Field("develop", description="The branch to put it on and update.")


class Result(BaseModel):
    text: str
    outcome: GitBranchPullOutcome


def run(context: ToolContext, params: Params) -> Result:
    branch = params.branch.strip()
    if not branch:
        raise ValidationError("Indica il branch.")
    repository = params.repository.strip()
    outcome = context.git.pull_repository_by_branch(context.require_project(), repository, branch)
    if outcome.status is GitBulkStatus.FAILED:
        raise UpstreamError(f"Repository {repository or 'progetto'} non aggiornato: {outcome.reason}")
    return Result(text=f"Branch {branch}:\n{outcome_line(outcome)}", outcome=outcome)


GIT_PULL_BY_BRANCH = params_tool(
    "git_pull_by_branch",
    "Put a git repository of the current project on a branch and update it in fast-forward (fetch, switch, pull --ff-only).",
    Params, run, writes=True,
)
