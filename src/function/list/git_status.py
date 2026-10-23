"""git_status function: branch, push/pull state and changed files of a
repository of the project, as plain text (no LLM). Empty ``repository`` =
the step input."""
from pydantic import BaseModel, Field

from function.context import FunctionContext
from function.spec import FunctionSpec
from models.domain.git import GitChange


class Params(BaseModel):
    repository: str = Field("", description="Cartella del repository nel progetto. Vuoto = usa l'input dello step.")


def run(context: FunctionContext, step_input: str, params: Params) -> str:
    repository = params.repository.strip() or step_input.strip()
    status = context.git.status(context.project_name, repository)
    header = f"Repository {repository or 'progetto'} · branch {status.branch or '(HEAD staccato)'}"
    if status.upstream:
        header += f" · {status.upstream}: {status.ahead} da pushare, {status.behind} da pullare"
    if status.is_clean:
        return f"{header}\nNessun file modificato."
    return f"{header}\n{len(status.changes)} file modificati:\n" + "\n".join(_line(change) for change in status.changes)


def _line(change: GitChange) -> str:
    stage = "staged" if change.staged and not change.unstaged else "non staged" if not change.staged else "in parte staged"
    renamed = f" (era {change.original_path})" if change.original_path else ""
    return f"- {change.path}{renamed}: {change.kind.value}, {stage}"


GIT_STATUS = FunctionSpec(
    name="git_status",
    description="File modificati, branch e commit da pushare/pullare di un repository del progetto (senza LLM).",
    params=Params,
    run=run,
)
