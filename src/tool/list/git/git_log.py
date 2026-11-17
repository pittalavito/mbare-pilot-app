"""git_log: the latest commits of a repository of the run's project, filtered
by author, message or commit, as text and as commits (the authors are declared
sensitive: a later agent step sees their aliases)."""
from pydantic import BaseModel, Field

from models.domain.git import GitCommit
from models.domain.masking import MaskRepositoryNames
from tool.context import ToolContext
from tool.spec import params_tool


class Params(BaseModel):
    repository: str = Field(..., description="Repository folder in the project ('' = the project folder).")
    limit: int = Field(20, ge=1, le=500, description="How many commits, newest first.")
    author: str = Field("", description="Only the commits of this author (name or email, also partial); '' = all.")
    message: str = Field("", description="Only the commits whose message contains this text (e.g. a ticket key); '' = all.")
    commit: str = Field("", description="Only this commit (a hash, also abbreviated); '' = not used.")


class Result(BaseModel):
    text: str
    repositories: MaskRepositoryNames
    commits: list[GitCommit]


def run(context: ToolContext, params: Params) -> Result:
    repository = params.repository.strip()
    commits = context.git.log(context.require_project(), repository, params.limit, author=params.author, message=params.message,
                              commit=params.commit.strip())
    name = repository or "progetto"
    if not commits:
        return Result(text=f"Repository {name}: nessun commit trovato.", repositories=[repository], commits=[])
    lines = "\n".join(f"- {c.short_hash} {c.date:%Y-%m-%d %H:%M} {c.author}: {c.subject}" for c in commits)
    return Result(text=f"Repository {name} · {len(commits)} commit:\n{lines}", repositories=[repository], commits=commits)


GIT_LOG = params_tool(
    "git_log",
    "Latest commits of a git repository of the current project, filtered by author, message or commit.",
    Params, run,
)
