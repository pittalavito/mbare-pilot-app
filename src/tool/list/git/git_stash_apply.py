"""git_stash_apply: apply a stash of a repository of the run's project again
(git stash apply). The stash stays in the list; conflicts are reported and
left to resolve by hand."""
from typing import Annotated

from datapizza.tools import Tool, tool

from core.error import AppError
from models.domain.masking import MaskCategory
from models.domain.tool import GitStashApplyResponse
from tool.context import ToolContext
from tool.list.git.errors import git_error
from tool.list.git.params import Repository
from tool.spec import ToolSpec

StashRef = Annotated[str, "The stash to apply: 'stash@{n}' or its number n; '' = the newest one."]


def build(context: ToolContext) -> Tool:

    @tool(name="git_stash_apply")
    def git_stash_apply(repository: Repository, stash: StashRef) -> str:
        """Apply a stash again to a git repository of the current project
        (git stash apply): the stash stays in the list. Refused if the
        repository has uncommitted changes to tracked files. If it conflicts,
        the conflicting files are listed and must be resolved by hand."""
        try:
            result = context.git.stash_apply(context.require_project(), repository, stash)
        except AppError as exc:
            return git_error(context, exc)
        context.register_sensitive(MaskCategory.REPOSITORY, repository)
        return GitStashApplyResponse(
            repository=repository, ref=result.ref, message=result.message, applied=not result.conflicts,
            files=result.files, conflicts=result.conflicts,
        ).model_dump_json()

    return git_stash_apply


GIT_STASH_APPLY = ToolSpec(
    name="git_stash_apply",
    description="Riapplica uno stash a un repository del progetto (git stash apply); lo stash resta nella lista.",
    build=build,
)
