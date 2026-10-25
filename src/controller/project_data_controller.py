"""A project's data (kept by the app apart from its code): markdown notes and
uploaded files, under /projects/{project}/notes and /projects/{project}/files.
A file is uploaded as the raw request body (PUT) and downloaded as bytes.

Agent tasks and todo lists are notes too (deleted as notes), read and written
as their template's fields under /agent-tasks and /todo-lists."""
from fastapi import APIRouter, Depends, Request, Response, status

from core.error import NotFoundError
from controller.dependencies import project_data_service
from service.project_data_service import ProjectDataService
from models.controller.project_data import (
    AgentTaskBody, AgentTaskResponse, DataFileResponse, NoteRequest, NoteResponse, TodoListBody, TodoListResponse,
)

router = APIRouter(prefix="/projects/{project}", tags=["project data"])


@router.get("/notes")
def list_notes(project: str, service: ProjectDataService = Depends(project_data_service)) -> list[DataFileResponse]:
    return [DataFileResponse.from_file(item) for item in service.list_notes(project)]


@router.get("/notes/{note}")
def read_note(project: str, note: str, service: ProjectDataService = Depends(project_data_service)) -> NoteResponse:
    return NoteResponse(name=note, content=service.read_note(project, note))


@router.put("/notes/{note}")
def save_note(project: str, note: str, request: NoteRequest, service: ProjectDataService = Depends(project_data_service)) -> DataFileResponse:
    """Create or overwrite."""
    return DataFileResponse.from_file(service.save_note(project, note, request.content))


@router.delete("/notes/{note}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(project: str, note: str, service: ProjectDataService = Depends(project_data_service)) -> Response:
    if not service.delete_note(project, note):
        raise NotFoundError(f"Nota non trovata: {note}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# -------------------------------------------------------------- typed notes

@router.get("/agent-tasks")
def list_agent_tasks(project: str, service: ProjectDataService = Depends(project_data_service)) -> list[AgentTaskResponse]:
    return [AgentTaskResponse.from_task(name, task) for name, task in service.agent_tasks(project)]


@router.post("/agent-tasks", status_code=status.HTTP_201_CREATED)
def create_agent_task(project: str, request: AgentTaskBody, service: ProjectDataService = Depends(project_data_service)) -> AgentTaskResponse:
    """A new note ``agent-task-<title>.md``; 409 when one with that name exists."""
    task = request.to_task()
    return AgentTaskResponse.from_task(service.create_agent_task(project, task), task)


@router.put("/agent-tasks/{note}")
def save_agent_task(project: str, note: str, request: AgentTaskBody, service: ProjectDataService = Depends(project_data_service)) -> AgentTaskResponse:
    task = request.to_task()
    service.save_agent_task(project, note, task)
    return AgentTaskResponse.from_task(note, task)


@router.get("/todo-lists")
def list_todo_lists(project: str, service: ProjectDataService = Depends(project_data_service)) -> list[TodoListResponse]:
    return [TodoListResponse.from_todo(name, todo) for name, todo in service.todo_lists(project)]


@router.post("/todo-lists", status_code=status.HTTP_201_CREATED)
def create_todo_list(project: str, request: TodoListBody, service: ProjectDataService = Depends(project_data_service)) -> TodoListResponse:
    """A new note ``todo-list-<title>.md``; 409 when one with that name exists."""
    todo = request.to_todo()
    return TodoListResponse.from_todo(service.create_todo_list(project, todo), todo)


@router.put("/todo-lists/{note}")
def save_todo_list(project: str, note: str, request: TodoListBody, service: ProjectDataService = Depends(project_data_service)) -> TodoListResponse:
    todo = request.to_todo()
    service.save_todo_list(project, note, todo)
    return TodoListResponse.from_todo(note, todo)


# -------------------------------------------------------------------- files

@router.get("/files")
def list_files(project: str, service: ProjectDataService = Depends(project_data_service)) -> list[DataFileResponse]:
    return [DataFileResponse.from_file(item) for item in service.list_files(project)]


@router.get("/files/{file_name}")
def download_file(project: str, file_name: str, service: ProjectDataService = Depends(project_data_service)) -> Response:
    return Response(content=service.read_file(project, file_name), media_type="application/octet-stream")


@router.put("/files/{file_name}")
async def upload_file(project: str, file_name: str, request: Request, service: ProjectDataService = Depends(project_data_service)) -> DataFileResponse:
    """The body is the file content; a file with the same name is overwritten."""
    return DataFileResponse.from_file(service.save_file(project, file_name, await request.body()))


@router.delete("/files/{file_name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(project: str, file_name: str, service: ProjectDataService = Depends(project_data_service)) -> Response:
    if not service.delete_file(project, file_name):
        raise NotFoundError(f"File non trovato: {file_name}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
