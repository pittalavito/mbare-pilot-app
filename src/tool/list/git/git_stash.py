"""git_stash: put aside the uncommitted changes to tracked files of a
repository of the run's project (git stash push), e.g. before a pull.
Untracked files stay where they are; restoring the stash is done by hand."""
from typing import Annotated

from datapizza.tools import Tool, tool

from core.error import AppError
from models.domain.masking import MaskCategory
from models.domain.tool import GitStashResponse
from tool.context import ToolContext
from tool.list.git.errors import git_error
from tool.list.git.params import Repository
from tool.spec import ToolSpec

StashMessage = Annotated[str, "Short description of the changes put aside; '' = an automatic one with date and time."]


def build(context: ToolContext) -> Tool:

    @tool(name="git_stash")
    def git_stash(repository: Repository, message: StashMessage) -> str:
        """Put aside the uncommitted changes to tracked files of a git
        repository of the current project (git stash push), leaving the
        working tree clean, e.g. before a pull. Untracked files are kept.
        Returns the stash created and the files put aside."""
        try:
            result = context.git.stash(context.require_project(), repository, message)
        except AppError as exc:
            return git_error(context, exc)
        context.register_sensitive(MaskCategory.REPOSITORY, repository)
        return GitStashResponse(
            repository=repository, stashed=result.stashed, ref=result.ref, message=result.message, files=result.files,
        ).model_dump_json()

    return git_stash


GIT_STASH = ToolSpec(
    name="git_stash",
    description="Mette da parte (git stash) le modifiche non committate ai file tracciati di un repository del progetto.",
    build=build,
)
