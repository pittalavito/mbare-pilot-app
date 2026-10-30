"""Git endpoints of a project (read-only), under /projects/{project}/git.
``path`` is a folder inside the project (``""`` = the project folder)."""
from fastapi import APIRouter, Depends

from controller.dependencies import git_service
from models.controller.git import CommitResponse, RepositoryResponse, StatusResponse
from service.git_service import GitService

router = APIRouter(prefix="/projects/{project}/git", tags=["git"])


@router.get("/repositories")
def list_repositories(project: str, service: GitService = Depends(git_service)) -> list[RepositoryResponse]:
    return [RepositoryResponse.from_repository(repository) for repository in service.repositories(project)]


@router.get("/log")
def git_log(project: str, path: str = "", limit: int = 50, author: str = "", message: str = "", commit: str = "",
            service: GitService = Depends(git_service)) -> list[CommitResponse]:
    """Newest first; ``author``, ``message`` and ``commit`` are optional filters."""
    commits = service.log(project, path, limit=limit, author=author, message=message, commit=commit)
    return [CommitResponse.from_commit(item) for item in commits]


@router.get("/status")
def git_status(project: str, path: str = "", service: GitService = Depends(git_service)) -> StatusResponse:
    return StatusResponse.from_status(service.status(project, path))
