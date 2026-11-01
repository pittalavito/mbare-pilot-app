"""git_pull_repo_by_branch function: one repository of the project on a
branch, updated from the remote (fetch, switch, pull --ff-only), as plain text
(no LLM). The same steps and reasons to skip as git_pull_all_repo_by_branch.

The step input is ``<repository> [<branch>]`` (e.g. ``api`` or ``api
feature/login``); with the ``repository`` param set it is just ``[<branch>]``.
A branch not in the input is the ``branch`` param. The step fails when the
repository could not be updated because of an error (not for a skip)."""
from pydantic import BaseModel, Field

from core.error import UpstreamError, ValidationError
from function.context import FunctionContext
from function.list.git_pull_all_repo_by_branch import outcome_line
from function.spec import FunctionResult, FunctionSpec
from models.domain.git import GitBranchPullOutcome, GitBulkStatus


class Params(BaseModel):
    repository: str = Field("", description="Cartella del repository nel progetto. Vuoto = la prima parola dell'input dello step.")
    branch: str = Field("develop", description="Il branch da usare quando l'input dello step non ne indica uno.")


class Result(FunctionResult):
    outcome: GitBranchPullOutcome


def run(context: FunctionContext, step_input: str, params: Params) -> Result:
    repository, branch = _target(step_input, params)
    outcome = context.git.pull_repository_by_branch(context.project_name, repository, branch)
    if outcome.status is GitBulkStatus.FAILED:
        raise UpstreamError(f"Repository {repository} non aggiornato: {outcome.reason}")
    return Result(text=f"Branch {branch}:\n{outcome_line(outcome)}", outcome=outcome)


def _target(step_input: str, params: Params) -> tuple[str, str]:
    """Repository and branch from the params and the step input."""
    words = step_input.split()
    repository = params.repository.strip()
    if not repository:
        if not words:
            raise ValidationError("Indica il repository: nel parametro o come input dello step (es. «api» o «api develop»).")
        repository, *words = words
    if len(words) > 1:
        raise ValidationError(f"Input non valido: {step_input.strip()!r}. Scrivi il repository e, se serve, il branch (es. «api develop»).")
    branch = words[0] if words else params.branch.strip()
    if not branch:
        raise ValidationError("Indica il branch: nell'input dello step o nel parametro.")
    return repository, branch


GIT_PULL_REPO_BY_BRANCH = FunctionSpec(
    name="git_pull_repo_by_branch",
    description="Porta un repository del progetto su un branch e lo aggiorna in fast-forward; input «<repository> [<branch>]» (senza LLM).",
    params=Params,
    run=run,
)
