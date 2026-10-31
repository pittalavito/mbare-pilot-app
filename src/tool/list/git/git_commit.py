"""git_commit: stage and commit changes in a repository of the run's project
(git add + git commit). The author of the commit is masked for the LLM."""
from typing import Annotated

from datapizza.tools import Tool, tool

from core.error import AppError
from models.domain.tool import GitCommitResponse, ToolErrorResponse
from tool.context import ToolContext
from tool.list.git.errors import git_error
from tool.list.git.params import Repository
from tool.spec import ToolSpec

CommitMessage = Annotated[str, "The commit message: a short summary line, optionally a blank line and a body."]
Files = Annotated[list[str], "Files to commit, relative to the repository root as git_status shows them; [] = every change in the repository folder."]


def build(context: ToolContext) -> Tool:

    @tool(name="git_commit")
    def git_commit(repository: Repository, message: CommitMessage, files: Files) -> GitCommitResponse | ToolErrorResponse:
        """Commit changes in a git repository of the current project (git add
        + git commit): the given files (new, changed or deleted) or all the
        changes. Files staged before are included too. Refused on a detached
        HEAD, with conflicts or with nothing to commit. Does not push."""
        try:
            result = context.git.commit(context.require_project(), repository, message, files)
        except AppError as exc:
            return git_error(context, exc)
        return GitCommitResponse(repository=repository, branch=result.branch, commit=result.commit, files=result.files)

    return git_commit


GIT_COMMIT = ToolSpec(
    name="git_commit",
    description="Fa git add + git commit in un repository del progetto, di file scelti o di tutte le modifiche (senza push).",
    build=build,
)
