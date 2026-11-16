"""git_check_clean («Prepara sviluppo»): the repositories to prepare
have no uncommitted changes to tracked files (new untracked files are fine);
otherwise the step fails, so Copilot does not start on top of them.

The repositories are those of ``targets`` (``<repository> <branch> [<base>]``
per line, domain/dev/inputs.py): in the automation, the run input."""
from pydantic import BaseModel, Field

from core.error import ConflictError
from domain.dev.inputs import ROOT, parse_prepare
from models.domain.git import GitChangeKind
from models.domain.masking import MaskRepositoryNames
from tool.context import ToolContext
from tool.spec import params_tool


class Params(BaseModel):
    targets: str = Field(..., description="One line per repository: «<repository> <branch> [<base>]» (. = the project folder), e.g. 'api feature/x develop'.")


class Result(BaseModel):
    text: str
    repositories: MaskRepositoryNames


def run(context: ToolContext, params: Params) -> Result:
    project = context.require_project()
    targets = parse_prepare(params.targets)
    dirty = []
    for target in targets:
        changes = [change.path for change in context.git.status(project, target.repository).changes
                   if change.kind is not GitChangeKind.UNTRACKED]
        if changes:
            shown = ", ".join(changes[:5]) + (f" e altri {len(changes) - 5}" if len(changes) > 5 else "")
            dirty.append(f"{target.repository or ROOT}: {shown}")
    if dirty:
        raise ConflictError("Modifiche non committate (committale o mettile da parte, poi riprova): " + "; ".join(dirty))
    names = [target.repository or ROOT for target in targets]
    return Result(text=f"Pulito: nessuna modifica non committata in {', '.join(names)}.", repositories=names)


GIT_CHECK_CLEAN = params_tool(
    "git_check_clean",
    "Fails if the given repositories have uncommitted changes to tracked files (the first step of «Prepara sviluppo»).",
    Params, run,
)
