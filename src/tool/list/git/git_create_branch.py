"""git_create_branch: create a branch in a repository of the run's project
and switch to it (git switch -c)."""
from typing import Annotated

from datapizza.tools import Tool, tool

from core.error import AppError
from models.domain.tool import GitCheckoutResponse, ToolErrorResponse
from tool.context import ToolContext
from tool.list.git.errors import git_error
from tool.list.git.params import Branch, Repository
from tool.spec import ToolSpec

StartPoint = Annotated[str, "Where the new branch starts: a branch, 'origin/<branch>' or a commit hash; '' = the current commit."]


def build(context: ToolContext) -> Tool:

    @tool(name="git_create_branch")
    def git_create_branch(repository: Repository, name: Branch, start_point: StartPoint) -> GitCheckoutResponse | ToolErrorResponse:
        """Create a new branch in a git repository of the current project and
        switch to it (git switch -c). Uncommitted changes come along. Refused
        if the branch already exists (use git_checkout)."""
        try:
            result = context.git.create_branch(context.require_project(), repository, name, start_point)
        except AppError as exc:
            return git_error(context, exc)
        return GitCheckoutResponse(repository=repository, **result.model_dump())

    return git_create_branch


GIT_CREATE_BRANCH = ToolSpec(
    name="git_create_branch",
    description="Crea un nuovo branch in un repository del progetto (dal commit corrente o da un altro) e ci passa.",
    build=build,
)
