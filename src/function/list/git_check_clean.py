"""git_check_clean function («Prepara sviluppo»): the repositories to prepare
have no uncommitted changes to tracked files (new untracked files are fine);
otherwise the step fails, so Copilot does not start on top of them.

The repositories are those of the run input (``<repository> <branch> [<base>]``
per line, domain/dev/inputs.py)."""
from core.error import ConflictError
from domain.dev.inputs import ROOT, parse_prepare
from function.context import FunctionContext
from function.spec import FunctionResult, FunctionSpec, NoParams
from models.domain.git import GitChangeKind
from models.domain.masking import MaskRepositoryNames


class Result(FunctionResult):
    repositories: MaskRepositoryNames


def run(context: FunctionContext, step_input: str, params: NoParams) -> Result:
    targets = parse_prepare(context.pipeline_input)
    dirty = []
    for target in targets:
        changes = [change.path for change in context.git.status(context.project_name, target.repository).changes
                   if change.kind is not GitChangeKind.UNTRACKED]
        if changes:
            shown = ", ".join(changes[:5]) + (f" e altri {len(changes) - 5}" if len(changes) > 5 else "")
            dirty.append(f"{target.repository or ROOT}: {shown}")
    if dirty:
        raise ConflictError("Modifiche non committate (committale o mettile da parte, poi riprova): " + "; ".join(dirty))
    names = [target.repository or ROOT for target in targets]
    return Result(text=f"Pulito: nessuna modifica non committata in {', '.join(names)}.", repositories=names)


GIT_CHECK_CLEAN = FunctionSpec(
    name="git_check_clean",
    description="Ferma la preparazione se i repository dell'input hanno modifiche non committate (senza LLM).",
    params=NoParams,
    run=run,
)
