"""git_log: the latest commits of a repository of the run's project, with
optional filters. The authors are registered as sensitive (masked for the LLM)."""
from typing import Annotated

from datapizza.tools import Tool, tool

from core.error import AppError
from models.domain.tool import GitLogResponse, ToolErrorResponse
from tool.context import ToolContext
from tool.list.git.errors import git_error
from tool.list.git.params import CommitHash, Repository
from tool.spec import ToolSpec

Limit = Annotated[int, "How many commits, 1-500 (e.g. 20)."]
Author = Annotated[str, "Only commits whose author name or email contains this text; '' = any."]
Message = Annotated[str, "Only commits whose message contains this text (e.g. a ticket key); '' = any."]


def build(context: ToolContext) -> Tool:

    @tool(name="git_log")
    def git_log(repository: Repository, limit: Limit, author: Author, message: Message, commit: CommitHash) -> GitLogResponse | ToolErrorResponse:
        """Latest commits of the current branch of a git repository of the
        current project, newest first (hash, author, date, subject). Filters
        combine: author, text in the message, a single commit hash."""
        try:
            commits = context.git.log(context.require_project(), repository, limit, author=author, message=message, commit=commit)
        except AppError as exc:
            return git_error(context, exc)
        return GitLogResponse(repository=repository, commits=commits)

    return git_log


GIT_LOG = ToolSpec(
    name="git_log",
    description="Ultimi commit di un repository del progetto, filtrabili per autore, messaggio o hash.",
    build=build,
)
