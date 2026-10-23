"""A project's data (kept by the app apart from its code): markdown notes and
uploaded files, under /projects/{project}/notes and /projects/{project}/files.
A file is uploaded as the raw request body (PUT) and downloaded as bytes."""
from fastapi import APIRouter, Depends, Request, Response, status

from controller.dependencies import project_data_service
from core.error import NotFoundError
from models.controller.project_data import DataFileResponse, NoteRequest, NoteResponse
from service.project_data_service import ProjectDataService

router = APIRouter(prefix="/projects/{project}", tags=["project data"])


# -------------------------------------------------------------------- notes

@router.get("/notes")
def list_notes(project: str, service: ProjectDataService = Depends(project_data_service)) -> list[DataFileResponse]:
    return [DataFileResponse.from_file(item) for item in service.list_notes(project)]


@router.get("/notes/{note}")
def read_note(project: str, note: str, service: ProjectDataService = Depends(project_data_service)) -> NoteResponse:
    return NoteResponse(name=note, content=service.read_note(project, note))


@router.put("/notes/{note}")
def save_note(project: str, note: str, request: NoteRequest,
              service: ProjectDataService = Depends(project_data_service)) -> DataFileResponse:
    """Create or overwrite."""
    return DataFileResponse.from_file(service.save_note(project, note, request.content))


@router.delete("/notes/{note}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(project: str, note: str, service: ProjectDataService = Depends(project_data_service)) -> Response:
    if not service.delete_note(project, note):
        raise NotFoundError(f"Nota non trovata: {note}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# -------------------------------------------------------------------- files

@router.get("/files")
def list_files(project: str, service: ProjectDataService = Depends(project_data_service)) -> list[DataFileResponse]:
    return [DataFileResponse.from_file(item) for item in service.list_files(project)]


@router.get("/files/{file_name}")
def download_file(project: str, file_name: str, service: ProjectDataService = Depends(project_data_service)) -> Response:
    return Response(content=service.read_file(project, file_name), media_type="application/octet-stream")


@router.put("/files/{file_name}")
async def upload_file(project: str, file_name: str, request: Request,
                      service: ProjectDataService = Depends(project_data_service)) -> DataFileResponse:
    """The body is the file content; a file with the same name is overwritten."""
    return DataFileResponse.from_file(service.save_file(project, file_name, await request.body()))


@router.delete("/files/{file_name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(project: str, file_name: str, service: ProjectDataService = Depends(project_data_service)) -> Response:
    if not service.delete_file(project, file_name):
        raise NotFoundError(f"File non trovato: {file_name}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
