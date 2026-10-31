"""git_pull_all_repo_by_branch function: every repository of the project on
``branch``, updated from the remote (fetch, switch, pull --ff-only), as plain
text (no LLM). Empty ``branch`` = the step input. Repositories with local
changes, without the branch or that cannot fast-forward are skipped; the step
fails only when every repository failed."""
from pydantic import BaseModel, Field

from core.error import UpstreamError, ValidationError
from function.context import FunctionContext
from function.spec import FunctionResult, FunctionSpec
from models.domain.git import GitBranchPullOutcome, GitBulkStatus

_LABELS = {
    GitBulkStatus.UPDATED: "aggiornato",
    GitBulkStatus.UP_TO_DATE: "già aggiornato",
    GitBulkStatus.SKIPPED: "saltato",
    GitBulkStatus.FAILED: "errore",
}


class Params(BaseModel):
    branch: str = Field("", description="Il branch su cui portare e aggiornare tutti i repository. Vuoto = usa l'input dello step.")


class Result(FunctionResult):
    outcomes: list[GitBranchPullOutcome]


def run(context: FunctionContext, step_input: str, params: Params) -> Result:
    branch = params.branch.strip() or step_input.strip()
    if not branch:
        raise ValidationError("Indica il branch: nel parametro o come input dello step.")
    outcomes = context.git.pull_all_by_branch(context.project_name, branch)
    if all(outcome.status is GitBulkStatus.FAILED for outcome in outcomes):
        raise UpstreamError("Nessun repository aggiornato:\n" + "\n".join(_line(outcome) for outcome in outcomes))
    counts = {status: sum(outcome.status is status for outcome in outcomes) for status in GitBulkStatus}
    summary = ", ".join(f"{count} {_LABELS[status]}" for status, count in counts.items() if count)
    lines = "\n".join(_line(outcome) for outcome in outcomes)
    return Result(text=f"Branch {branch} su {len(outcomes)} repository: {summary}.\n{lines}", outcomes=outcomes)


def _line(outcome: GitBranchPullOutcome) -> str:
    name = outcome.repository or "progetto"
    switched = f" (era su {outcome.previous or 'HEAD staccato'})" if outcome.switched else ""
    if outcome.status is GitBulkStatus.UPDATED:
        return f"- {name}{switched}: aggiornato, {len(outcome.commits)} commit nuovi"
    if outcome.status is GitBulkStatus.UP_TO_DATE:
        return f"- {name}{switched}: già aggiornato"
    return f"- {name}{switched}: {_LABELS[outcome.status]}, {outcome.reason}"


GIT_PULL_ALL_REPO_BY_BRANCH = FunctionSpec(
    name="git_pull_all_repo_by_branch",
    description="Porta tutti i repository del progetto su un branch e li aggiorna in fast-forward; salta quelli con modifiche locali (senza LLM).",
    params=Params,
    run=run,
)
