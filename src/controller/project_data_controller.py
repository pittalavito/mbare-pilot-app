"""A project's data (kept by the app apart from its code): markdown notes and
uploaded files, under /projects/{project}/notes and /projects/{project}/files.
A file is uploaded as the raw request body (PUT) and downloaded as bytes.

Agent tasks and activities are notes too (deleted as notes: an agent task is
then unlinked from its activities), read and written as their template's
fields under /agent-tasks and /activities. Code and context
references, linked to them by name, under /references (deleting one unlinks it);
/code-todos gathers the code's todoMbarePilot comments into one of them."""
from fastapi import APIRouter, Depends, Request, Response, status

from controller.dependencies import code_todo_service, project_data_service
from core.error import NotFoundError
from models.controller.project_data import (
    ActivityBody,
    ActivityResponse,
    AgentTaskBody,
    AgentTaskResponse,
    CodeTodoScanResponse,
    DataFileResponse,
    DataSettingsBody,
    NoteRequest,
    NoteResponse,
    ReferenceBody,
    ReferenceCreateBody,
    ReferenceResponse,
)
from models.domain.note import NoteType
from service.code_todo_service import CodeTodoService
from service.project_data_service import ProjectDataService

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


@router.get("/activities")
def list_activities(project: str, service: ProjectDataService = Depends(project_data_service)) -> list[ActivityResponse]:
    return [ActivityResponse.from_activity(name, activity) for name, activity in service.activities(project)]


@router.post("/activities", status_code=status.HTTP_201_CREATED)
def create_activity(project: str, request: ActivityBody, service: ProjectDataService = Depends(project_data_service)) -> ActivityResponse:
    """A new note ``attivita-<title>.md``; 409 when one with that name exists."""
    activity = request.to_activity()
    return ActivityResponse.from_activity(service.create_activity(project, activity), activity)


@router.put("/activities/{note}")
def save_activity(project: str, note: str, request: ActivityBody, service: ProjectDataService = Depends(project_data_service)) -> ActivityResponse:
    activity = request.to_activity()
    service.save_activity(project, note, activity)
    return ActivityResponse.from_activity(note, activity)


# --------------------------------------------------------------- references

@router.get("/references")
def list_references(project: str, service: ProjectDataService = Depends(project_data_service)) -> list[ReferenceResponse]:
    """Every code and context reference, with what links it."""
    links = service.linked_from(project)
    return [ReferenceResponse.from_reference(name, kind, item, links.get(name, [])) for name, kind, item in service.references(project)]


@router.post("/references", status_code=status.HTTP_201_CREATED)
def create_reference(project: str, request: ReferenceCreateBody, service: ProjectDataService = Depends(project_data_service)) -> ReferenceResponse:
    """A new note ``code-reference-<title>.md`` or ``context-reference-<title>.md`` (409 when it exists); link it from a task or activity."""
    kind, reference = NoteType(request.kind), request.to_reference()
    return ReferenceResponse.from_reference(service.create_reference(project, kind, reference), kind, reference, [])


@router.put("/references/{note}")
def save_reference(project: str, note: str, request: ReferenceBody, service: ProjectDataService = Depends(project_data_service)) -> ReferenceResponse:
    reference = request.to_reference()
    service.save_reference(project, note, reference)
    kind, _ = service.reference(project, note)
    return ReferenceResponse.from_reference(note, kind, reference, service.linked_from(project).get(note, []))


@router.post("/code-todos")
def scan_code_todos(project: str, service: CodeTodoService = Depends(code_todo_service)) -> CodeTodoScanResponse:
    """Gather the todoMbarePilot{...} comments of the code into the note
    ``code-reference-todo-mbare-pilot.md`` (409 when a note with that name was written by hand)."""
    return CodeTodoScanResponse(**service.save(project).model_dump())


@router.delete("/references/{note}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reference(project: str, note: str, service: ProjectDataService = Depends(project_data_service)) -> Response:
    """The reference and its links from the agent tasks and activities."""
    if not service.delete_reference(project, note):
        raise NotFoundError(f"Riferimento non trovato: {note}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ----------------------------------------------------------------- settings

@router.get("/data-settings")
def data_settings(project: str, service: ProjectDataService = Depends(project_data_service)) -> DataSettingsBody:
    """What the Dati tab shows (the default types until the project chooses)."""
    return DataSettingsBody(visible_note_types=service.visible_note_types(project), files_visible=service.files_visible(project))


@router.put("/data-settings")
def save_data_settings(project: str, request: DataSettingsBody, service: ProjectDataService = Depends(project_data_service)) -> DataSettingsBody:
    return DataSettingsBody(visible_note_types=service.save_visible_note_types(project, request.visible_note_types),
                            files_visible=service.save_files_visible(project, request.files_visible))


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
