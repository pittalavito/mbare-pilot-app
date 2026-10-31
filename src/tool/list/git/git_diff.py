"""git_diff: what changed in a repository of the run's project, not staged
yet, staged, or in one commit. The patch is cut to stay readable."""
from typing import Annotated

from datapizza.tools import Tool, tool

from core.error import AppError
from models.domain.tool import GitDiffResponse, ToolErrorResponse
from tool.context import ToolContext
from tool.list.git.errors import git_error
from tool.list.git.params import CommitHash, Repository
from tool.spec import ToolSpec

Staged = Annotated[bool, "True = the changes already staged (git add-ed); false = the ones not staged yet. Ignored with a commit."]


def build(context: ToolContext) -> Tool:

    @tool(name="git_diff")
    def git_diff(repository: Repository, staged: Staged, commit: CommitHash) -> GitDiffResponse | ToolErrorResponse:
        """Diff of a git repository of the current project: the uncommitted
        changes (not staged, or staged) or those of one commit. Returns the
        changed files with lines added/deleted and the unified patch (cut
        when very long). New untracked files are listed apart."""
        try:
            result = context.git.diff(context.require_project(), repository, staged=staged, commit=commit)
        except AppError as exc:
            return git_error(context, exc)
        of = f"commit {commit.strip()}" if commit.strip() else "staged" if staged else "unstaged"
        return GitDiffResponse(repository=repository, of=of, **result.model_dump())

    return git_diff


GIT_DIFF = ToolSpec(
    name="git_diff",
    description="Diff di un repository del progetto: modifiche non staged, staged o di un commit.",
    build=build,
)
