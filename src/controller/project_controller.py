"""Projects endpoints — everything under /projects."""
from fastapi import APIRouter, Depends, Response, status

from controller.dependencies import project_service
from service.project_service import ProjectService
from models.controller.project import CreateFromScratchRequest, OpenFolderRequest, ProjectOptionsResponse, ProjectResponse, UpdateProjectRequest
from models.domain.chat import EmbeddingModelName
from models.domain.project import Project

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("")
def list_projects(service: ProjectService = Depends(project_service)) -> list[ProjectResponse]:
    """Every project, most recent first."""
    return [_response(service, project) for project in service.list_projects()]


@router.get("/options")
def project_options() -> ProjectOptionsResponse:
    return ProjectOptionsResponse(embedding_models=list(EmbeddingModelName))


@router.get("/{name}")
def get_project(name: str, service: ProjectService = Depends(project_service)) -> ProjectResponse:
    return _response(service, service.get_project(name))


@router.post("/open-folder", status_code=status.HTTP_201_CREATED)
def open_folder(request: OpenFolderRequest, service: ProjectService = Depends(project_service)) -> ProjectResponse:
    """Register an existing folder as a project (the folder is not touched)."""
    folder = service.folders.resolve(request.folder)
    name = request.name.strip() or folder.name
    return _response(service, service.open_folder(name, request.description.strip(), folder))


@router.post("/from-scratch", status_code=status.HTTP_201_CREATED)
def create_from_scratch(request: CreateFromScratchRequest, service: ProjectService = Depends(project_service)) -> ProjectResponse:
    """Create a new folder in ``parent`` and register it as a project."""
    folder_name = request.folder_name.strip() or request.name.strip()
    project = service.create_from_scratch(request.name.strip(), request.description.strip(), request.parent, folder_name)
    return _response(service, project)


@router.patch("/{name}")
def update_project(name: str, request: UpdateProjectRequest, service: ProjectService = Depends(project_service)) -> ProjectResponse:
    project = service.update(name, description=request.description, embedding_model=request.embedding_model)
    return _response(service, project)


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
def remove_project(name: str, service: ProjectService = Depends(project_service)) -> Response:
    """Remove the project and what it owns in the DB; its folders on disk stay."""
    service.get_project(name)  # 404 when absent
    service.remove(name)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _response(service: ProjectService, project: Project) -> ProjectResponse:
    return ProjectResponse.from_project(project, folder_exists=service.folder_exists(project))
