"""git_status function: branch, push/pull state and changed files of a
repository of the project, as plain text (no LLM). Empty ``repository`` =
the step input; ``*`` = every repository of the project, one after the other."""
from pydantic import BaseModel, Field

from core.error import AppError, ValidationError
from function.context import FunctionContext
from function.spec import FunctionResult, FunctionSpec
from models.domain.git import GitChange
from models.domain.masking import MaskRepositoryNames

ALL = "*"


class Params(BaseModel):
    repository: str = Field("", description="Cartella del repository nel progetto. Vuoto = usa l'input dello step; * = tutti i repository del progetto.")


class Result(FunctionResult):
    repositories: MaskRepositoryNames


def run(context: FunctionContext, step_input: str, params: Params) -> Result:
    repository = params.repository.strip() or step_input.strip()
    if repository != ALL:
        return Result(text=_status(context, repository), repositories=[repository])
    found = [repo.path for repo in context.git.repositories(context.project_name)]
    if not found:
        raise ValidationError("Nessun repository git nella cartella del progetto.")
    texts = [_status_or_error(context, path) for path in found]
    return Result(text=f"{len(found)} repository nel progetto.\n\n" + "\n\n".join(texts), repositories=found)


def _status(context: FunctionContext, repository: str) -> str:
    status = context.git.status(context.project_name, repository)
    header = f"Repository {repository or 'progetto'} · branch {status.branch or '(HEAD staccato)'}"
    if status.upstream:
        header += f" · {status.upstream}: {status.ahead} da pushare, {status.behind} da pullare"
    if status.is_clean:
        return f"{header}\nNessun file modificato."
    lines = "\n".join(_line(change) for change in status.changes)
    return f"{header}\n{len(status.changes)} file modificati:\n{lines}"


def _status_or_error(context: FunctionContext, repository: str) -> str:
    try:
        return _status(context, repository)
    except AppError as exc:
        return f"Repository {repository or 'progetto'} · stato non letto: {exc}"


def _line(change: GitChange) -> str:
    stage = "staged" if change.staged and not change.unstaged else "non staged" if not change.staged else "in parte staged"
    renamed = f" (era {change.original_path})" if change.original_path else ""
    return f"- {change.path}{renamed}: {change.kind.value}, {stage}"


GIT_STATUS = FunctionSpec(
    name="git_status",
    description="File modificati, branch e commit da pushare/pullare di un repository del progetto, o di tutti con * (senza LLM).",
    params=Params,
    run=run,
)
