"""git_push: push the current branch of a repository of the run's project.
Never forced; a branch without upstream is published to origin."""
from datapizza.tools import Tool, tool

from core.error import AppError
from models.domain.tool import GitPushResponse, ToolErrorResponse
from tool.context import ToolContext
from tool.list.git.errors import git_error
from tool.list.git.params import Repository
from tool.spec import ToolSpec


def build(context: ToolContext) -> Tool:

    @tool(name="git_push")
    def git_push(repository: Repository) -> GitPushResponse | ToolErrorResponse:
        """Push the current branch of a git repository of the current project
        to its upstream (never forced). A branch without upstream is pushed to
        origin with the same name and starts tracking it. Refused when the
        remote has commits not pulled yet. Returns the commits sent."""
        try:
            result = context.git.push(context.require_project(), repository)
        except AppError as exc:
            return git_error(context, exc)
        return GitPushResponse(repository=repository, pushed=bool(result.commits), **result.model_dump())

    return git_push


GIT_PUSH = ToolSpec(
    name="git_push",
    description="Pusha il branch corrente di un repository del progetto (mai forzato); senza upstream lo pubblica su origin.",
    build=build,
)
