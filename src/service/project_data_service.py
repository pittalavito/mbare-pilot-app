"""A project's data, kept by the app apart from the project's code, under
``<MBARE_PILOT_HOME>/project/<slug>/``: ``notes/*.md`` (notes written in the app:
generic, or typed by their name and written with a template: agent tasks, todo lists),
``files/*`` (uploaded documents) and ``context/*.md`` (the project's context,
written by hand: what read_context gives the chatbot, and the RAG will index)."""
from datetime import datetime, timezone

from collections.abc import Callable

from pydantic import BaseModel

from core.error import ConflictError, NotFoundError, ValidationError
from domain.project.data_paths import (
    CONTEXT_DIR, FILES_DIR, NOTE_SUFFIX, NOTES_DIR, data_file_name, note_file_name, note_type, project_slug, typed_note_file_name,
)
from domain.project.note_templates import parse_agent_task, parse_todo_list, render_agent_task, render_todo_list
from models.domain.note import AgentTask, NoteType, TodoList
from models.domain.project import ProjectDataFile, ProjectDataKind
from models.store.files import StoredFile
from service.store_service import StoreService


class ProjectDataService:

    def __init__(self, store_service: StoreService):
        self._store = store_service

    # ----------------------------------------------------------------- notes
    def list_notes(self, project_name: str) -> list[ProjectDataFile]:
        return self._list(project_name, NOTES_DIR, ProjectDataKind.NOTE)

    def read_note(self, project_name: str, note_name: str) -> str:
        return self._store.read_file(self._id(project_name, NOTES_DIR, note_file_name(note_name))).decode("utf-8")

    def save_note(self, project_name: str, note_name: str, content: str) -> ProjectDataFile:
        """Create or overwrite the note."""
        stored = self._store.save_file(self._id(project_name, NOTES_DIR, note_file_name(note_name)), content.encode("utf-8"))
        return _to_data_file(stored, ProjectDataKind.NOTE)

    def delete_note(self, project_name: str, note_name: str) -> bool:
        return self._store.delete_file(self._id(project_name, NOTES_DIR, note_file_name(note_name)))

    # ----------------------------------------------------------- typed notes
    def agent_tasks(self, project_name: str) -> list[tuple[str, AgentTask]]:
        """The agent tasks, as (note name, task)."""
        return self._typed_notes(project_name, NoteType.AGENT_TASK, parse_agent_task)

    def agent_task(self, project_name: str, note_name: str) -> AgentTask:
        """One agent task; NotFoundError when missing, ValidationError when the note is of another type."""
        name = note_file_name(note_name)
        if note_type(name) != NoteType.AGENT_TASK:
            raise ValidationError(f"{name} non è un agent task.")
        return parse_agent_task(self.read_note(project_name, name), _title(name))

    def create_agent_task(self, project_name: str, task: AgentTask) -> str:
        """A new note named after the title (``agent-task-<title>.md``); returns its name."""
        return self._create_typed(project_name, NoteType.AGENT_TASK, task.title, render_agent_task(task))

    def save_agent_task(self, project_name: str, note_name: str, task: AgentTask) -> None:
        """Rewrite an existing agent task (its name stays, also when the title changes)."""
        self._save_typed(project_name, NoteType.AGENT_TASK, note_name, render_agent_task(task))

    def todo_lists(self, project_name: str) -> list[tuple[str, TodoList]]:
        """The todo lists, as (note name, list)."""
        return self._typed_notes(project_name, NoteType.TODO_LIST, parse_todo_list)

    def create_todo_list(self, project_name: str, todo: TodoList) -> str:
        return self._create_typed(project_name, NoteType.TODO_LIST, todo.title, render_todo_list(todo))

    def save_todo_list(self, project_name: str, note_name: str, todo: TodoList) -> None:
        self._save_typed(project_name, NoteType.TODO_LIST, note_name, render_todo_list(todo))

    def _typed_notes[T: BaseModel](self, project_name: str, kind: NoteType, parse: Callable[[str, str], T]) -> list[tuple[str, T]]:
        notes = [note for note in self.list_notes(project_name) if note.note_type == kind]
        return [(note.name, parse(self.read_note(project_name, note.name), _title(note.name))) for note in notes]

    def _create_typed(self, project_name: str, kind: NoteType, title: str, content: str) -> str:
        name = typed_note_file_name(kind, title)
        if self._store.get_file(self._id(project_name, NOTES_DIR, name)) is not None:
            raise ConflictError(f"Esiste già una nota {name}: cambia il titolo.")
        return self.save_note(project_name, name, content).name

    def _save_typed(self, project_name: str, kind: NoteType, note_name: str, content: str) -> None:
        name = note_file_name(note_name)
        if note_type(name) != kind:
            raise ValidationError(f"{name} non è una nota di tipo {kind}.")
        if self._store.get_file(self._id(project_name, NOTES_DIR, name)) is None:
            raise NotFoundError(f"Nota non trovata: {name}")
        self.save_note(project_name, name, content)

    # ----------------------------------------------------------------- files
    def list_files(self, project_name: str) -> list[ProjectDataFile]:
        return self._list(project_name, FILES_DIR, ProjectDataKind.FILE)

    def read_file(self, project_name: str, file_name: str) -> bytes:
        return self._store.read_file(self._id(project_name, FILES_DIR, data_file_name(file_name)))

    def save_file(self, project_name: str, file_name: str, data: bytes) -> ProjectDataFile:
        """Store an uploaded file (same name = overwritten)."""
        stored = self._store.save_file(self._id(project_name, FILES_DIR, data_file_name(file_name)), data)
        return _to_data_file(stored, ProjectDataKind.FILE)

    def delete_file(self, project_name: str, file_name: str) -> bool:
        return self._store.delete_file(self._id(project_name, FILES_DIR, data_file_name(file_name)))

    # --------------------------------------------------------------- context
    def context(self, project_name: str) -> dict[str, str]:
        """The project's context: the ``.md`` files of ``context/``, name -> content."""
        prefix = f"{project_slug(self._project(project_name))}/{CONTEXT_DIR}"
        return {
            stored.file_id.rsplit("/", 1)[-1]: self._store.read_file(stored.file_id).decode("utf-8")
            for stored in sorted(self._store.list_files(prefix), key=lambda item: item.file_id.lower())
            if stored.file_id.endswith(NOTE_SUFFIX)
        }

    # --------------------------------------------------------------- helpers
    def _project(self, project_name: str) -> str:
        project = self._store.get_project(project_name)
        if project is None:
            raise NotFoundError(f"Progetto non trovato: {project_name}")
        return project.name

    def _id(self, project_name: str, folder: str, file_name: str) -> str:
        return f"{project_slug(self._project(project_name))}/{folder}/{file_name}"

    def _list(self, project_name: str, folder: str, kind: ProjectDataKind) -> list[ProjectDataFile]:
        prefix = f"{project_slug(self._project(project_name))}/{folder}"
        return sorted(
            (_to_data_file(stored, kind) for stored in self._store.list_files(prefix)),
            key=lambda item: item.name.lower(),
        )


def _to_data_file(stored: StoredFile, kind: ProjectDataKind) -> ProjectDataFile:
    name = stored.file_id.rsplit("/", 1)[-1]
    return ProjectDataFile(
        name=name,
        kind=kind,
        size=stored.size,
        modified_at=datetime.fromtimestamp(stored.mtime_ns / 1e9, tz=timezone.utc),
        note_type=note_type(name) if kind == ProjectDataKind.NOTE else None,
    )


def _title(note_name: str) -> str:
    """The title of a typed note without its ``# title`` line: its name, without prefix and suffix."""
    stem = note_name.removesuffix(NOTE_SUFFIX)
    return stem.split("-", 2)[-1].replace("-", " ") or stem
