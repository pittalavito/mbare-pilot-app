"""git_status: branch, push/pull state and changed files of a repository of
the run's project, or of all of them with ``*``: first the ones with something
to report (changed files, commits to push or pull, detached HEAD, status not
read), then the others. As text (an automation step's output) and the
repositories it read."""
from pydantic import BaseModel, Field

from core.error import AppError, ValidationError
from models.domain.git import GitChange, GitStatus
from models.domain.masking import MaskRepositoryNames
from tool.context import ToolContext
from tool.spec import params_tool

ALL = "*"


class Params(BaseModel):
    repository: str = Field(..., description="Repository folder in the project ('' = the project folder); * = every repository of the project.")


class Result(BaseModel):
    text: str = Field(..., description="The status, ready to read.")
    repositories: MaskRepositoryNames


def run(context: ToolContext, params: Params) -> Result:
    project = context.require_project()
    repository = params.repository.strip()
    if repository != ALL:
        return Result(text=_report(context, project, repository)[0], repositories=[repository])
    found = [repo.path for repo in context.git.repositories(project)]
    if not found:
        raise ValidationError("Nessun repository git nella cartella del progetto.")
    reports = [_report_or_error(context, project, path) for path in found]
    to_check = [text for text, attention in reports if attention]
    fine = [text for text, attention in reports if not attention]
    summary = f"{len(to_check)} da guardare, {len(fine)} a posto" if to_check else "tutti a posto"
    return Result(text=f"{len(found)} repository nel progetto: {summary}.\n\n" + "\n\n".join(to_check + fine), repositories=found)


def _report(context: ToolContext, project: str, repository: str) -> tuple[str, bool]:
    """The status as text, and whether it has something to report."""
    status = context.git.status(project, repository)
    attention = not status.is_clean or status.ahead > 0 or status.behind > 0 or status.branch is None
    return _text(repository, status), attention


def _text(repository: str, status: GitStatus) -> str:
    header = f"Repository {repository or 'progetto'} · branch {status.branch or '(HEAD staccato)'}"
    if status.upstream:
        header += f" · {status.upstream}: {status.ahead} da pushare, {status.behind} da pullare"
    if status.is_clean:
        return f"{header}\nNessun file modificato."
    lines = "\n".join(_line(change) for change in status.changes)
    return f"{header}\n{len(status.changes)} file modificati:\n{lines}"


def _report_or_error(context: ToolContext, project: str, repository: str) -> tuple[str, bool]:
    try:
        return _report(context, project, repository)
    except AppError as exc:
        return f"Repository {repository or 'progetto'} · stato non letto: {exc}", True


def _line(change: GitChange) -> str:
    stage = "staged" if change.staged and not change.unstaged else "non staged" if not change.staged else "in parte staged"
    renamed = f" (era {change.original_path})" if change.original_path else ""
    return f"- {change.path}{renamed}: {change.kind.value}, {stage}"


GIT_STATUS = params_tool(
    "git_status",
    "Working-tree status of a git repository of the current project, or of all of them with *: branch, commits to push/pull "
    "against the upstream and the changed files.",
    Params, run,
)
