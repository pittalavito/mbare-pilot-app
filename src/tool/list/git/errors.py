"""Errors of the git tools go back to the agent as JSON instead of stopping the
run, with the repositories it can use so it can retry with a valid one.

Messages from git and GitService contain local paths: the project folder
becomes ``<progetto>`` and the user's home ``~``, so the LLM never sees where
the code lives on this PC. The repository names are declared sensitive in
ToolErrorResponse, so the agent layer masks them."""
import re
from pathlib import Path

from core.error import AppError
from models.domain.tool import ToolErrorResponse
from tool.context import ToolContext


def git_error(context: ToolContext, exc: AppError) -> ToolErrorResponse:
    message = hide_local_paths(context, str(exc))
    repositories = _repositories(context)
    if repositories:
        message += f" Repository disponibili: {', '.join(repositories)}."
    return ToolErrorResponse(error=message, repositories=repositories)


def _repositories(context: ToolContext) -> list[str]:
    """Repository paths of the run's project ('' shown as ''); none without a project."""
    if context.project_name is None:
        return []
    try:
        repositories = context.git.repositories(context.project_name)
    except AppError:
        return []
    return [repo.path or "''" for repo in repositories]


def hide_local_paths(context: ToolContext, text: str) -> str:
    """The project folder → ``<progetto>``, the home folder → ``~``: with ``\\``
    or ``/`` separators, case-insensitive (git writes paths both ways)."""
    folder = context.git.project_folder(context.project_name) if context.project_name else None
    for path, placeholder in ((folder, "<progetto>"), (Path.home(), "~")):
        if path is not None:
            text = _path_pattern(path).sub(placeholder, text)
    return text


def _path_pattern(path: Path) -> re.Pattern:
    parts = [re.escape(part.rstrip("\\/")) for part in path.parts if part.rstrip("\\/")]
    return re.compile(r"[\\/]".join(parts), re.IGNORECASE)
