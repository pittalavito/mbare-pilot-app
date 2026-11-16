"""git_fetch: ``git fetch --all --prune`` of a repository of the run's
project, or of all of them with ``*``: where each current branch stands
against its upstream afterwards, as text."""
from pydantic import BaseModel, Field

from core.error import AppError, ValidationError
from models.domain.masking import MaskRepositoryNames
from tool.context import ToolContext
from tool.spec import params_tool

ALL = "*"


class Params(BaseModel):
    repository: str = Field(..., description="Repository folder in the project ('' = the project folder); * = every repository of the project.")


class Result(BaseModel):
    text: str
    repositories: MaskRepositoryNames


def run(context: ToolContext, params: Params) -> Result:
    project = context.require_project()
    repository = params.repository.strip()
    if repository != ALL:
        return Result(text=_fetch(context, project, repository), repositories=[repository])
    found = [repo.path for repo in context.git.repositories(project)]
    if not found:
        raise ValidationError("Nessun repository git nella cartella del progetto.")
    texts = [_fetch_or_error(context, project, path) for path in found]
    return Result(text=f"Fetch di {len(found)} repository.\n" + "\n".join(texts), repositories=found)


def _fetch(context: ToolContext, project: str, repository: str) -> str:
    result = context.git.fetch(project, repository)
    line = f"- {repository or 'progetto'} · branch {result.branch or '(HEAD staccato)'}"
    if not result.upstream:
        return f"{line} · nessun upstream"
    return f"{line} · {result.upstream}: {result.ahead} da pushare, {result.behind} da pullare"


def _fetch_or_error(context: ToolContext, project: str, repository: str) -> str:
    try:
        return _fetch(context, project, repository)
    except AppError as exc:
        return f"- {repository or 'progetto'} · fetch non riuscito: {exc}"


GIT_FETCH = params_tool(
    "git_fetch",
    "git fetch --all --prune of a git repository of the current project, or of all of them with *: commits to push/pull afterwards.",
    Params, run,
)
