"""Errors of the git tools go back to the agent as JSON instead of stopping the
run, with the repositories it can use so it can retry with a valid one."""
from core.error import AppError
from models.domain.tool import ToolErrorResponse
from tool.context import ToolContext


def git_error(context: ToolContext, exc: AppError) -> str:
    message = str(exc)
    repositories = _repositories(context)
    if repositories:
        message += f" Repository disponibili: {', '.join(repositories)}."
    return ToolErrorResponse(error=message).model_dump_json()


def _repositories(context: ToolContext) -> list[str]:
    """Repository paths of the run's project ('' shown as ''); none without a project."""
    if context.project_name is None:
        return []
    try:
        return [repo.path or "''" for repo in context.git.repositories(context.project_name)]
    except AppError:
        return []
