"""The ``todoMbarePilot{description}`` comments of a project's code, gathered
into one code reference (domain/project/code_todos.py).

``scan`` reads the files git knows in each repository of the project
(tracked, plus new ones not ignored: ``.gitignore`` is respected), skipping
binaries, files that are not UTF-8, big files and the task folders for
Copilot (``mbare-pilot/``). ``save`` writes the result as the note
``code-reference-todo-mbare-pilot.md``: one per project, rewritten by every
scan (its links from tasks and lists stay, the name does not change)."""
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from core.error import ConflictError, NotFoundError
from core.observability import LogPrefix, observed
from domain.project import code_todos, task_folder
from domain.project.data_paths import typed_note_file_name
from models.domain.code_todo import CodeTodo, CodeTodoScan
from models.domain.note import NoteType
from service.git_service import GitService
from service.project_data_service import ProjectDataService

MAX_FILE_BYTES = 1_000_000
"""Bigger files are skipped (generated code, data, minified bundles)."""
_BINARY_PROBE = 8192


class CodeTodoService:

    def __init__(self, git_service: GitService, project_data_service: ProjectDataService,
                 clock: Callable[[], datetime] = datetime.now):
        self._git = git_service
        self._data = project_data_service
        self._clock = clock

    def scan(self, project_name: str) -> dict[str, list[CodeTodo]]:
        """The comments by file (path relative to the project folder, ``/``
        separators); files without comments are left out."""
        found: dict[str, list[CodeTodo]] = {}
        for repository in self._git.repositories(project_name):
            folder = self._git.repository_folder(project_name, repository.path)
            for path in self._git.files(project_name, repository.path):
                if task_folder.is_task_path(path):
                    continue
                text = _read_text(folder / path)
                todos = code_todos.find(text) if text else []
                if todos:
                    found[f"{repository.path}/{path}" if repository.path else path] = todos
        return found

    @observed(LogPrefix.CODE_TODO_SERVICE)
    def save(self, project_name: str) -> CodeTodoScan:
        """Scan and write the note. Nothing found: an existing note says so,
        none is created. ConflictError when a note with that name exists and
        was not written by the scan (it is left as it is)."""
        todos = self.scan(project_name)
        name = typed_note_file_name(NoteType.CODE_REFERENCE, code_todos.TITLE)
        try:
            existing = self._data.reference(project_name, name)[1]
        except NotFoundError:
            existing = None
        if existing is not None and existing.source != code_todos.SOURCE:
            raise ConflictError(f"Esiste già {name}, scritto a mano: rinominalo o cancellalo per far scrivere lì la scansione.")
        counts = {"files": len(todos), "comments": sum(len(items) for items in todos.values())}
        if existing is None and not todos:
            return CodeTodoScan(note=None, created=False, **counts)
        reference = code_todos.reference(todos, self._clock())
        if existing is None:
            return CodeTodoScan(note=self._data.create_reference(project_name, NoteType.CODE_REFERENCE, reference), created=True, **counts)
        self._data.save_reference(project_name, name, reference)
        return CodeTodoScan(note=name, created=False, **counts)


def _read_text(path: Path) -> str:
    """The file as text; ``""`` when it is missing, big, binary or not UTF-8."""
    try:
        if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            return ""
        data = path.read_bytes()
    except OSError:
        return ""
    if b"\0" in data[:_BINARY_PROBE]:
        return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return ""
