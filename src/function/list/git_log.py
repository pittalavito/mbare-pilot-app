"""git_log function: the latest commits of a repository of the project as
plain text (no LLM), e.g. to feed an agent step that writes release notes.
The authors are declared sensitive: a later agent step sees their aliases."""
from pydantic import BaseModel, Field

from function.context import FunctionContext
from function.spec import FunctionResult, FunctionSpec
from models.domain.git import GitCommit
from models.domain.masking import MaskRepositoryNames


class Params(BaseModel):
    repository: str = Field("", description="Cartella del repository nel progetto. Vuoto = usa l'input dello step.")
    limit: int = Field(20, ge=1, le=500, description="Quanti commit, dal più recente.")
    author: str = Field("", description="Solo i commit di questo autore (nome o email, anche in parte). Vuoto = tutti.")
    message: str = Field("", description="Solo i commit il cui messaggio contiene questo testo (es. la chiave di un ticket). Vuoto = tutti.")


class Result(FunctionResult):
    repositories: MaskRepositoryNames
    commits: list[GitCommit]


def run(context: FunctionContext, step_input: str, params: Params) -> Result:
    repository = params.repository.strip() or step_input.strip()
    commits = context.git.log(context.project_name, repository, params.limit, author=params.author, message=params.message)
    name = repository or "progetto"
    if not commits:
        return Result(text=f"Repository {name}: nessun commit trovato.", repositories=[repository], commits=[])
    lines = "\n".join(f"- {c.short_hash} {c.date:%Y-%m-%d %H:%M} {c.author}: {c.subject}" for c in commits)
    return Result(text=f"Repository {name} · {len(commits)} commit:\n{lines}", repositories=[repository], commits=commits)


GIT_LOG = FunctionSpec(
    name="git_log",
    description="Ultimi commit di un repository del progetto, filtrabili per autore o messaggio, come testo (senza LLM).",
    params=Params,
    run=run,
)
