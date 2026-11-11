"""git_checkout_branches function («Prepara sviluppo»): every repository of
the run input on its branch, up to date. For each line ``<repository>
<branch> [<base>]`` (domain/dev/inputs.py), after a fetch:

- the branch exists (locally or on a remote): checkout, then pull **only in
  fast-forward** when it has an upstream;
- it does not exist: created from ``<base>`` (``origin/<base>`` when the
  remote has it, the local one otherwise); without a base it is an error.

The first repository that cannot be prepared (uncommitted changes, a branch
that diverged from its upstream, a branch or base that is not there) fails
the step, so Copilot does not start; the ones after it are not touched."""
from core.error import AppError, ConflictError, NotFoundError
from domain.dev.inputs import ROOT, parse_prepare
from function.context import FunctionContext
from function.spec import FunctionResult, FunctionSpec, NoParams
from models.domain.dev import PrepareTarget
from models.domain.masking import MaskRepositoryNames


class Result(FunctionResult):
    repositories: MaskRepositoryNames


def run(context: FunctionContext, step_input: str, params: NoParams) -> Result:
    targets = parse_prepare(context.pipeline_input)
    lines = []
    for target in targets:
        name = target.repository or ROOT
        try:
            lines.append(f"- {name}: {_prepare(context, target)}")
        except AppError as exc:
            done = ("\n" + "\n".join(lines)) if lines else ""
            raise ConflictError(f"{name} non preparato: {exc}{done}") from exc
    return Result(text="Branch:\n" + "\n".join(lines), repositories=[target.repository or ROOT for target in targets])


def _prepare(context: FunctionContext, target: PrepareTarget) -> str:
    git, project, path = context.git, context.project_name, target.repository
    git.fetch(project, path)
    branches = git.branches(project, path)
    local = {branch.name for branch in branches.local}
    remote = {name.split("/", 1)[-1] for name in branches.remote}
    if target.branch in local | remote:
        git.checkout(project, path, target.branch)
        if not git.status(project, path).upstream:
            return f"su {target.branch} (senza upstream: niente pull)"
        pulled = git.pull_fast_forward(project, path)
        return f"su {target.branch}, " + ("già aggiornato" if pulled.up_to_date else f"aggiornato ({len(pulled.commits)} commit)")
    if not target.base:
        raise NotFoundError(f"il branch {target.branch} non c'è: indica da quale branch crearlo")
    if f"origin/{target.base}" in branches.remote:
        start = f"origin/{target.base}"
    elif target.base in local:
        start = target.base
    else:
        raise NotFoundError(f"il branch base {target.base} non c'è, né locale né su origin")
    git.create_branch(project, path, target.branch, start, track=False)  # a feature branch does not track its base
    return f"creato {target.branch} da {start}"


GIT_CHECKOUT_BRANCHES = FunctionSpec(
    name="git_checkout_branches",
    description="Porta i repository dell'input sul loro branch (lo crea dal base se manca) e li aggiorna in fast-forward (senza LLM).",
    params=NoParams,
    run=run,
)
