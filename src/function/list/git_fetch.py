"""git_fetch function: ``git fetch --all --prune`` of a repository of the
project, or of all of them with ``*``, as plain text (no LLM): where each
current branch stands against its upstream afterwards."""
from pydantic import BaseModel, Field

from core.error import AppError, ValidationError
from function.context import FunctionContext
from function.spec import FunctionResult, FunctionSpec
from models.domain.masking import MaskRepositoryNames

ALL = "*"


class Params(BaseModel):
    repository: str = Field("", description="Cartella del repository nel progetto. Vuoto = usa l'input dello step; * = tutti i repository del progetto.")


class Result(FunctionResult):
    repositories: MaskRepositoryNames


def run(context: FunctionContext, step_input: str, params: Params) -> Result:
    repository = params.repository.strip() or step_input.strip()
    if repository != ALL:
        return Result(text=_fetch(context, repository), repositories=[repository])
    found = [repo.path for repo in context.git.repositories(context.project_name)]
    if not found:
        raise ValidationError("Nessun repository git nella cartella del progetto.")
    texts = [_fetch_or_error(context, path) for path in found]
    return Result(text=f"Fetch di {len(found)} repository.\n" + "\n".join(texts), repositories=found)


def _fetch(context: FunctionContext, repository: str) -> str:
    result = context.git.fetch(context.project_name, repository)
    line = f"- {repository or 'progetto'} · branch {result.branch or '(HEAD staccato)'}"
    if not result.upstream:
        return f"{line} · nessun upstream"
    return f"{line} · {result.upstream}: {result.ahead} da pushare, {result.behind} da pullare"


def _fetch_or_error(context: FunctionContext, repository: str) -> str:
    try:
        return _fetch(context, repository)
    except AppError as exc:
        return f"- {repository or 'progetto'} · fetch non riuscito: {exc}"


GIT_FETCH = FunctionSpec(
    name="git_fetch",
    description="git fetch --all --prune di un repository del progetto, o di tutti con *: commit da pushare/pullare dopo il fetch (senza LLM).",
    params=Params,
    run=run,
)
