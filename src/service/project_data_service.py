"""A project's data, kept by the app apart from the project's code, under
``<MBARE_PILOT_HOME>/project/<slug>/``: ``notes/*.md`` (notes written in the app:
generic, or typed by their name and written with a template: agent tasks, activities,
and the code and context references they link by name),
``files/*`` (uploaded documents), ``context/*.md`` (the project's context,
written by hand: what read_context gives the chatbot, and the RAG will index)
and ``copilot/<session>/`` (an agent task and its references, for Copilot)."""
from collections.abc import Callable
from datetime import datetime, timezone

from pydantic import BaseModel

from core.error import ConflictError, NotFoundError, ValidationError
from core.observability import LogPrefix, log_info, log_warning
from domain.project.data_paths import (
    CONTEXT_DIR,
    FILES_DIR,
    NOTE_PREFIXES,
    NOTE_SUFFIX,
    NOTES_DIR,
    data_file_name,
    file_link,
    is_file_link,
    note_file_name,
    note_type,
    project_slug,
    typed_note_file_name,
)
from domain.project.note_templates import (
    parse_activity,
    parse_agent_task,
    parse_reference,
    render_activity,
    render_agent_task,
    render_reference,
)
from models.domain.note import Activity, AgentTask, NoteType, Reference, TaskLink
from models.domain.project import DEFAULT_VISIBLE_NOTE_TYPES, ProjectDataFile, ProjectDataKind
from models.store.files import StoredFile
from service.store.project_file_store import ProjectFileStore
from service.store.project_store import ProjectStore


class ProjectDataService:

    def __init__(self, files: ProjectFileStore, projects: ProjectStore):
        self._files = files
        self._projects = projects

    # ----------------------------------------------------------------- notes
    def list_notes(self, project_name: str) -> list[ProjectDataFile]:
        return self._list(project_name, NOTES_DIR, ProjectDataKind.NOTE)

    def read_note(self, project_name: str, note_name: str) -> str:
        return self._files.read(self._id(project_name, NOTES_DIR, note_file_name(note_name))).decode("utf-8")

    def save_note(self, project_name: str, note_name: str, content: str) -> ProjectDataFile:
        """Create or overwrite the note."""
        stored = self._files.save(self._id(project_name, NOTES_DIR, note_file_name(note_name)), content.encode("utf-8"))
        return _to_data_file(stored, ProjectDataKind.NOTE)

    def delete_note(self, project_name: str, note_name: str) -> bool:
        """An agent task is also unlinked from the activities it was born from,
        a note (or a reference) from the tasks and activities that link it."""
        name = note_file_name(note_name)
        kind = note_type(name)
        if kind == NoteType.AGENT_TASK:
            for activity_name, activity in self.activities(project_name):
                if name in activity.agent_tasks:
                    self.save_activity(project_name, activity_name, activity.model_copy(
                        update={"agent_tasks": [task for task in activity.agent_tasks if task != name]}))
        elif kind == NoteType.GENERIC or kind.is_reference:
            self._unlink(project_name, name)
        return self._files.delete(self._id(project_name, NOTES_DIR, name))

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
        _check_references(task.references)
        return self._create_typed(project_name, NoteType.AGENT_TASK, task.title, render_agent_task(task))

    def save_agent_task(self, project_name: str, note_name: str, task: AgentTask) -> None:
        """Rewrite an existing agent task (its name stays, also when the title changes)."""
        _check_references(task.references)
        self._save_typed(project_name, NoteType.AGENT_TASK, note_name, render_agent_task(task))

    def activities(self, project_name: str) -> list[tuple[str, Activity]]:
        """The activities, as (note name, activity)."""
        return self._typed_notes(project_name, NoteType.ACTIVITY, parse_activity)

    def activity(self, project_name: str, note_name: str) -> Activity:
        """One activity; NotFoundError when missing, ValidationError when the note is of another type."""
        name = note_file_name(note_name)
        if note_type(name) != NoteType.ACTIVITY:
            raise ValidationError(f"{name} non è un'attività.")
        return parse_activity(self.read_note(project_name, name), _title(name))

    def create_activity(self, project_name: str, activity: Activity) -> str:
        """A new note named after the title (``attivita-<title>.md``); returns its name."""
        _check_links(activity)
        return self._create_typed(project_name, NoteType.ACTIVITY, activity.title, render_activity(activity))

    def save_activity(self, project_name: str, note_name: str, activity: Activity) -> None:
        """Rewrite an existing activity (its name stays, also when the title changes)."""
        _check_links(activity)
        self._save_typed(project_name, NoteType.ACTIVITY, note_name, render_activity(activity))

    def link_agent_task(self, project_name: str, activity_name: str, task_name: str) -> None:
        """The agent task among the activity's ones (once); both must exist."""
        task = note_file_name(task_name)
        self.agent_task(project_name, task)
        activity = self.activity(project_name, activity_name)
        if task not in activity.agent_tasks:
            self.save_activity(project_name, activity_name, activity.model_copy(update={"agent_tasks": [*activity.agent_tasks, task]}))

    def migrate_todo_lists(self, project_name: str) -> int:
        """The old todo lists (``todo-list-<title>.md``) become activities
        (``attivita-<title>.md``): same items and references, description
        empty, status from the items. One whose new name is taken stays as it
        is (logged). Returns how many were moved."""
        moved = 0
        for note in self.list_notes(project_name):
            if not note.name.startswith(_OLD_TODO_LIST_PREFIX):
                continue
            new = NOTE_PREFIXES[NoteType.ACTIVITY] + note.name.removeprefix(_OLD_TODO_LIST_PREFIX)
            if self._files.get(self._id(project_name, NOTES_DIR, new)) is not None:
                log_warning(LogPrefix.PROJECT_SERVICE, "Todo list %s non migrata: %s esiste già", note.name, new)
                continue
            activity = parse_activity(self.read_note(project_name, note.name), _title(new))
            self.save_note(project_name, new, render_activity(activity))
            self._files.delete(self._id(project_name, NOTES_DIR, note.name))
            moved += 1
        if moved:
            log_info(LogPrefix.PROJECT_SERVICE, "%s: %d todo list diventate attività", project_name, moved)
        return moved

    # ------------------------------------------------------------ references
    def references(self, project_name: str) -> list[tuple[str, NoteType, Reference]]:
        """The code and context references, as (note name, type, reference)."""
        notes = [note for note in self.list_notes(project_name) if note.note_type and note.note_type.is_reference]
        return [(note.name, note.note_type, parse_reference(self.read_note(project_name, note.name), _title(note.name))) for note in notes]

    def reference(self, project_name: str, note_name: str) -> tuple[NoteType, Reference]:
        name = note_file_name(note_name)
        kind = note_type(name)
        if not kind.is_reference:
            raise ValidationError(f"{name} non è un riferimento.")
        return kind, parse_reference(self.read_note(project_name, name), _title(name))

    def create_reference(self, project_name: str, kind: NoteType, reference: Reference) -> str:
        """A new note ``code-reference-<title>.md`` or ``context-reference-<title>.md``; returns its name."""
        if not kind.is_reference:
            raise ValidationError(f"{kind} non è un tipo di riferimento.")
        return self._create_typed(project_name, kind, reference.title, render_reference(reference, kind == NoteType.CODE_REFERENCE))

    def save_reference(self, project_name: str, note_name: str, reference: Reference) -> None:
        """Rewrite an existing reference (name and type stay)."""
        kind = note_type(note_file_name(note_name))
        if not kind.is_reference:
            raise ValidationError(f"{note_file_name(note_name)} non è un riferimento.")
        self._save_typed(project_name, kind, note_name, render_reference(reference, kind == NoteType.CODE_REFERENCE))

    def delete_reference(self, project_name: str, note_name: str) -> bool:
        """The reference, and its links from the agent tasks and activities."""
        name = note_file_name(note_name)
        if not note_type(name).is_reference:
            raise ValidationError(f"{name} non è un riferimento.")
        return self.delete_note(project_name, name)

    def _unlink(self, project_name: str, link: str) -> None:
        """``link`` (a reference, a note, ``files/<name>``) out of every task's and activity's references."""
        for task_name, task in self.agent_tasks(project_name):
            if link in task.references:
                self.save_agent_task(project_name, task_name, task.model_copy(update={"references": [r for r in task.references if r != link]}))
        for activity_name, activity in self.activities(project_name):
            if link in activity.references:
                self.save_activity(project_name, activity_name, activity.model_copy(
                    update={"references": [r for r in activity.references if r != link]}))

    def import_reference(self, project_name: str, kind: NoteType, reference: Reference, link_to: list[str] = ()) -> tuple[str, bool]:
        """A reference copied from elsewhere (Jira, Confluence...): created, or
        refreshed when the note with that name was copied from the same
        ``source_url``; then linked from the agent tasks and todo lists in
        ``link_to``. Returns (name, created). ConflictError when the name is
        taken by another reference."""
        name = typed_note_file_name(kind, reference.title)
        created = self._files.get(self._id(project_name, NOTES_DIR, name)) is None
        if created:
            self.create_reference(project_name, kind, reference)
        else:
            if self.reference(project_name, name)[1].source_url != reference.source_url:
                raise ConflictError(f"Esiste già un riferimento {name} che non viene da {reference.source_url}.")
            self.save_reference(project_name, name, reference)
        self.link_reference(project_name, name, list(link_to))
        return name, created

    def link_reference(self, project_name: str, reference_name: str, parents: list[str]) -> None:
        """Link the reference from each agent task / activity (by name) that does not link it yet."""
        for parent in parents:
            kind = note_type(note_file_name(parent))
            if kind == NoteType.AGENT_TASK:
                task = self.agent_task(project_name, parent)
                if reference_name not in task.references:
                    self.save_agent_task(project_name, parent, task.model_copy(update={"references": [*task.references, reference_name]}))
            elif kind == NoteType.ACTIVITY:
                activity = self.activity(project_name, parent)
                if reference_name not in activity.references:
                    self.save_activity(project_name, parent, activity.model_copy(update={"references": [*activity.references, reference_name]}))
            else:
                raise ValidationError(f"{parent} non è un agent task né un'attività: non può collegare riferimenti.")

    def linked_from(self, project_name: str) -> dict[str, list[str]]:
        """Reference name → the agent tasks and activities that link it."""
        links: dict[str, list[str]] = {}
        for parent, item in [*self.agent_tasks(project_name), *self.activities(project_name)]:
            for name in item.references:
                links.setdefault(name, []).append(parent)
        return links

    def _typed_notes[T: BaseModel](self, project_name: str, kind: NoteType, parse: Callable[[str, str], T]) -> list[tuple[str, T]]:
        notes = [note for note in self.list_notes(project_name) if note.note_type == kind]
        return [(note.name, parse(self.read_note(project_name, note.name), _title(note.name))) for note in notes]

    def _create_typed(self, project_name: str, kind: NoteType, title: str, content: str) -> str:
        name = typed_note_file_name(kind, title)
        if self._files.get(self._id(project_name, NOTES_DIR, name)) is not None:
            raise ConflictError(f"Esiste già una nota {name}: cambia il titolo.")
        return self.save_note(project_name, name, content).name

    def _save_typed(self, project_name: str, kind: NoteType, note_name: str, content: str) -> None:
        name = note_file_name(note_name)
        if note_type(name) != kind:
            raise ValidationError(f"{name} non è una nota di tipo {kind}.")
        if self._files.get(self._id(project_name, NOTES_DIR, name)) is None:
            raise NotFoundError(f"Nota non trovata: {name}")
        self.save_note(project_name, name, content)

    # ---------------------------------------------------------- copilot folder
    def task_links(self, project_name: str, task_note: str) -> list[TaskLink]:
        """What an agent task links (references, notes, uploaded files), in
        its order, with a title: what Copilot lists through MCP. NotFoundError
        when the task is gone."""
        links = []
        for name in self.agent_task(project_name, task_note).references:
            if is_file_link(name):
                found = self._files.get(self._id(project_name, FILES_DIR, data_file_name(name))) is not None
                links.append(TaskLink(name=name, kind="file", title=data_file_name(name), found=found))
                continue
            note = note_file_name(name)
            kind = note_type(note)
            try:
                text = self.read_note(project_name, note)
            except NotFoundError:
                links.append(TaskLink(name=name, kind=_LINK_KINDS.get(kind, "note"), title=_title(note), found=False))
                continue
            title = parse_reference(text, _title(note)).title if kind.is_reference else _heading(text) or note
            links.append(TaskLink(name=name, kind=_LINK_KINDS.get(kind, "note"), title=title))
        return links

    def task_link_text(self, project_name: str, task_note: str, name: str) -> str:
        """The content of something the task links, as text: a note as it is,
        an uploaded file decoded as UTF-8 (a binary one: a line saying so).
        NotFoundError when the task does not link ``name`` or it no longer exists."""
        if name.strip() not in self.agent_task(project_name, task_note).references:
            raise NotFoundError(f"{name} non è collegato al task: usa i nomi che dà list_references.")
        if is_file_link(name):
            data = self._files.read(self._id(project_name, FILES_DIR, data_file_name(name)))
            try:
                return data.decode("utf-8")
            except UnicodeDecodeError:
                return f"(file binario di {len(data)} byte: non leggibile come testo)"
        return self.read_note(project_name, name)

    # -------------------------------------------------------------- settings
    def visible_note_types(self, project_name: str) -> list[NoteType]:
        """The note types the Dati tab shows (the project's choice, else the default ones)."""
        project = self._projects.get(self._project(project_name))
        return project.visible_note_types if project.visible_note_types is not None else list(DEFAULT_VISIBLE_NOTE_TYPES)

    def save_visible_note_types(self, project_name: str, kinds: list[NoteType]) -> list[NoteType]:
        """In the order of NoteType, each once."""
        project = self._projects.get(self._project(project_name))
        ordered = [kind for kind in NoteType if kind in set(kinds)]
        self._projects.save(project.model_copy(update={"visible_note_types": ordered}))
        return ordered

    def files_visible(self, project_name: str) -> bool:
        """Whether the Dati tab shows the uploaded files."""
        return self._projects.get(self._project(project_name)).files_visible

    def save_files_visible(self, project_name: str, visible: bool) -> bool:
        project = self._projects.get(self._project(project_name))
        self._projects.save(project.model_copy(update={"files_visible": visible}))
        return visible

    # ----------------------------------------------------------------- files
    def list_files(self, project_name: str) -> list[ProjectDataFile]:
        return self._list(project_name, FILES_DIR, ProjectDataKind.FILE)

    def read_file(self, project_name: str, file_name: str) -> bytes:
        return self._files.read(self._id(project_name, FILES_DIR, data_file_name(file_name)))

    def save_file(self, project_name: str, file_name: str, data: bytes) -> ProjectDataFile:
        """Store an uploaded file (same name = overwritten)."""
        stored = self._files.save(self._id(project_name, FILES_DIR, data_file_name(file_name)), data)
        return _to_data_file(stored, ProjectDataKind.FILE)

    def delete_file(self, project_name: str, file_name: str) -> bool:
        """Also unlinked from the tasks and activities that link it."""
        self._unlink(project_name, file_link(file_name))
        return self._files.delete(self._id(project_name, FILES_DIR, data_file_name(file_name)))

    # --------------------------------------------------------------- context
    def context(self, project_name: str) -> dict[str, str]:
        """The project's context: the ``.md`` files of ``context/``, name -> content."""
        prefix = f"{project_slug(self._project(project_name))}/{CONTEXT_DIR}"
        return {
            stored.file_id.rsplit("/", 1)[-1]: self._files.read(stored.file_id).decode("utf-8")
            for stored in sorted(self._files.list(prefix), key=lambda item: item.file_id.lower())
            if stored.file_id.endswith(NOTE_SUFFIX)
        }

    # --------------------------------------------------------------- helpers
    def _project(self, project_name: str) -> str:
        project = self._projects.get(project_name)
        if project is None:
            raise NotFoundError(f"Progetto non trovato: {project_name}")
        return project.name

    def _id(self, project_name: str, folder: str, file_name: str) -> str:
        return f"{project_slug(self._project(project_name))}/{folder}/{file_name}"

    def _list(self, project_name: str, folder: str, kind: ProjectDataKind) -> list[ProjectDataFile]:
        prefix = f"{project_slug(self._project(project_name))}/{folder}"
        return sorted(
            (_to_data_file(stored, kind) for stored in self._files.list(prefix)),
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


_OLD_TODO_LIST_PREFIX = "todo-list-"
"""The name of a todo list before they became activities (migrate_todo_lists)."""


def _check_links(activity: Activity) -> None:
    _check_references(activity.references)
    for name in activity.agent_tasks:
        if note_type(note_file_name(name)) != NoteType.AGENT_TASK:
            raise ValidationError(f"{name} non è un agent task: un'attività collega solo agent-task-….")


def _check_references(names: list[str]) -> None:
    """What a task or an activity links as reference: reference notes, other
    notes by name, uploaded files as ``files/<name>`` (a missing one is
    tolerated: it may have been removed by hand). Not agent tasks nor activities."""
    for name in names:
        if is_file_link(name):
            if file_link(name) != name.strip():  # exactly files/<name>: no folders, no spaces around
                raise ValidationError(f"Collegamento a un file non valido: {name!r} (files/<nome>).")
        elif note_type(note_file_name(name)) not in (NoteType.GENERIC, NoteType.CODE_REFERENCE, NoteType.CONTEXT_REFERENCE):
            raise ValidationError(f"{name} non si può collegare come riferimento: solo riferimenti, note e file (files/<nome>).")


_LINK_KINDS = {NoteType.CODE_REFERENCE: "code", NoteType.CONTEXT_REFERENCE: "context"}


def _heading(text: str) -> str:
    """The ``# title`` of a markdown note; ``""`` without one."""
    return next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), "")


def _title(note_name: str) -> str:
    """The title of a typed note without its ``# title`` line: its name, without prefix and suffix."""
    stem = note_name.removesuffix(NOTE_SUFFIX)
    return stem.split("-", 2)[-1].replace("-", " ") or stem
