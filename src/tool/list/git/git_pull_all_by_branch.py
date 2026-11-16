"""git_pull_all_by_branch: every repository of the run's project on
``branch``, updated from the remote (fetch, switch, pull --ff-only).
Repositories with local changes, without the branch or that cannot
fast-forward are skipped with the reason; it fails only when every repository failed."""
from pydantic import BaseModel, Field

from core.error import UpstreamError, ValidationError
from models.domain.git import GitBranchPullOutcome, GitBulkStatus
from tool.context import ToolContext
from tool.list.git.errors import hide_local_paths
from tool.spec import params_tool

_LABELS = {
    GitBulkStatus.UPDATED: "aggiornato",
    GitBulkStatus.UP_TO_DATE: "già aggiornato",
    GitBulkStatus.SKIPPED: "saltato",
    GitBulkStatus.FAILED: "errore",
}


class Params(BaseModel):
    branch: str = Field(..., description="The branch to put every repository on and update, e.g. 'develop'.")


class Result(BaseModel):
    text: str
    outcomes: list[GitBranchPullOutcome]


def run(context: ToolContext, params: Params) -> Result:
    branch = params.branch.strip()
    if not branch:
        raise ValidationError("Indica il branch.")
    outcomes = context.git.pull_all_by_branch(context.require_project(), branch)
    for outcome in outcomes:
        outcome.reason = hide_local_paths(context, outcome.reason)
    if all(outcome.status is GitBulkStatus.FAILED for outcome in outcomes):
        raise UpstreamError("Nessun repository aggiornato:\n" + "\n".join(outcome_line(outcome) for outcome in outcomes))
    counts = {status: sum(outcome.status is status for outcome in outcomes) for status in GitBulkStatus}
    summary = ", ".join(f"{count} {_LABELS[status]}" for status, count in counts.items() if count)
    lines = "\n".join(outcome_line(outcome) for outcome in outcomes)
    return Result(text=f"Branch {branch} su {len(outcomes)} repository: {summary}.\n{lines}", outcomes=outcomes)


def outcome_line(outcome: GitBranchPullOutcome) -> str:
    """One line of the outcome of a repository (also used by git_pull_by_branch)."""
    name = outcome.repository or "progetto"
    switched = f" (era su {outcome.previous or 'HEAD staccato'})" if outcome.switched else ""
    if outcome.status is GitBulkStatus.UPDATED:
        return f"- {name}{switched}: aggiornato, {len(outcome.commits)} commit nuovi"
    if outcome.status is GitBulkStatus.UP_TO_DATE:
        return f"- {name}{switched}: già aggiornato"
    return f"- {name}{switched}: {_LABELS[outcome.status]}, {outcome.reason}"


GIT_PULL_ALL_BY_BRANCH = params_tool(
    "git_pull_all_by_branch",
    "For every git repository of the current project: fetch, switch to the branch and pull it in fast-forward. Repositories with "
    "uncommitted changes, without the branch or that cannot fast-forward are skipped with the reason.",
    Params, run, writes=True,
)
