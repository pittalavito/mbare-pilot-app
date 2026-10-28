import pytest

from core.error import ConflictError, NotFoundError, ValidationError
from domain.project.data_paths import data_file_name, note_file_name, project_slug
from domain.project.folder_browser import FolderBrowser
from models.domain.note import AgentTask, ChecklistItem, NoteType, TaskStatus, TodoItem, TodoList, TodoPriority
from models.domain.project import Project, ProjectDataKind, ProjectSource
from service.project_data_service import ProjectDataService
from service.project_service import ProjectService


@pytest.fixture
def data_service(store_service, files_repository):
    store_service.save_project(Project(name="My App", source=ProjectSource.FOLDER, root_path="/code/my-app"))
    return ProjectDataService(store_service)


# ------------------------------------------------------------------- naming

@pytest.mark.parametrize("name, slug", [("My App", "my-app"), ("  ACME__2  ", "acme-2"), ("---", "project")])
def test_project_slug(name, slug):
    assert project_slug(name) == slug


def test_note_and_file_names():
    assert note_file_name("Setup") == "Setup.md"
    assert note_file_name(" decisioni.md ") == "decisioni.md"
    assert data_file_name("C:\\Users\\me\\report.pdf") == "report.pdf"
    assert data_file_name("dir/sub/spec.docx") == "spec.docx"


@pytest.mark.parametrize("bad", ["", "..", ".hidden", "a:b", "a?b", "a/b"])
def test_invalid_note_names(bad):
    with pytest.raises(ValidationError):
        note_file_name(bad)


@pytest.mark.parametrize("bad", ["", "..", ".env", "a|b", "a*b"])
def test_invalid_file_names(bad):
    with pytest.raises(ValidationError):
        data_file_name(bad)


# ------------------------------------------------------------------ service

def test_notes_round_trip(data_service, files_repository):
    data_service.save_note("My App", "Setup", "# Setup\nInstalla uv.")

    [note] = data_service.list_notes("My App")
    assert (note.name, note.kind) == ("Setup.md", ProjectDataKind.NOTE)
    assert data_service.read_note("My App", "Setup") == "# Setup\nInstalla uv."
    assert (files_repository.root / "my-app" / "notes" / "Setup.md").is_file()

    data_service.save_note("My App", "Setup.md", "nuovo testo")
    assert data_service.read_note("My App", "Setup.md") == "nuovo testo"
    assert data_service.delete_note("My App", "Setup") is True
    assert data_service.list_notes("My App") == []


def test_files_round_trip(data_service, files_repository):
    data_service.save_file("My App", "C:\\tmp\\report.pdf", b"%PDF")

    [item] = data_service.list_files("My App")
    assert (item.name, item.kind, item.size) == ("report.pdf", ProjectDataKind.FILE, 4)
    assert data_service.read_file("My App", "report.pdf") == b"%PDF"
    assert (files_repository.root / "my-app" / "files" / "report.pdf").is_file()
    assert data_service.list_notes("My App") == []
    assert data_service.delete_file("My App", "report.pdf") is True



def test_typed_notes_are_notes_named_by_type(data_service, files_repository):
    name = data_service.create_agent_task("My App", AgentTask(title="Refactor login", criteria=[ChecklistItem(text="test verdi")]))
    data_service.create_todo_list("My App", TodoList(title="Rilascio", items=[TodoItem(text="tag", priority=TodoPriority.LOW)]))
    data_service.save_note("My App", "decisioni", "# Decisioni")

    assert name == "agent-task-refactor-login.md"
    assert (files_repository.root / "my-app" / "notes" / name).read_text(encoding="utf-8").startswith("# Refactor login\n\nStato: da fare")
    assert {note.name: note.note_type for note in data_service.list_notes("My App")} == {
        "agent-task-refactor-login.md": NoteType.AGENT_TASK, "decisioni.md": NoteType.GENERIC, "todo-list-rilascio.md": NoteType.TODO_LIST,
    }
    [(_, todo)] = data_service.todo_lists("My App")
    assert todo.items[0].priority == TodoPriority.LOW

    data_service.save_agent_task("My App", name, AgentTask(title="Refactor login (v2)", status=TaskStatus.DONE))
    assert data_service.agent_tasks("My App") == [(name, AgentTask(title="Refactor login (v2)", status=TaskStatus.DONE))]


def test_typed_notes_refuse_duplicates_other_types_and_missing_ones(data_service):
    data_service.create_todo_list("My App", TodoList(title="Rilascio"))

    with pytest.raises(ConflictError):
        data_service.create_todo_list("My App", TodoList(title="rilascio!"))
    with pytest.raises(ValidationError):
        data_service.save_agent_task("My App", "todo-list-rilascio.md", AgentTask(title="x"))
    with pytest.raises(NotFoundError):
        data_service.save_todo_list("My App", "todo-list-altro.md", TodoList(title="x"))


def test_unknown_project(data_service):
    with pytest.raises(NotFoundError):
        data_service.list_notes("ghost")


def test_projects_with_the_same_slug_conflict(store_service, tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    projects = ProjectService(store_service, FolderBrowser([tmp_path]))
    projects.open_folder("My App", "", tmp_path / "a")

    with pytest.raises(ConflictError):
        projects.open_folder("my-app", "", tmp_path / "b")


# ---------------------------------------------------------------- references

def test_references_are_linked_to_tasks_and_todo_lists_many_to_many(data_service):
    from models.domain.note import Reference

    code = data_service.create_reference("My App", NoteType.CODE_REFERENCE, Reference(title="Login", repository="api", path="a.py"))
    context = data_service.create_reference("My App", NoteType.CONTEXT_REFERENCE, Reference(title="Procedura", source="jira"))
    task = data_service.create_agent_task("My App", AgentTask(title="Fix", references=[code, context]))
    todo = data_service.create_todo_list("My App", TodoList(title="Rilascio", references=[context]))

    assert (code, context) == ("code-reference-login.md", "context-reference-procedura.md")
    assert [(name, kind) for name, kind, _ in data_service.references("My App")] == [(code, NoteType.CODE_REFERENCE), (context, NoteType.CONTEXT_REFERENCE)]
    assert data_service.reference("My App", code)[1].path == "a.py"
    assert data_service.linked_from("My App") == {code: [task], context: [task, todo]}

    data_service.save_reference("My App", context, Reference(title="Procedura v2"))
    assert data_service.reference("My App", context)[1].title == "Procedura v2"
    assert data_service.delete_reference("My App", context)
    assert data_service.agent_task("My App", task).references == [code]  # unlinked everywhere
    assert data_service.todo_lists("My App")[0][1].references == []


def test_only_references_can_be_linked_and_saved_as_references(data_service):
    from models.domain.note import Reference

    with pytest.raises(ValidationError, match="non è un riferimento"):
        data_service.create_agent_task("My App", AgentTask(title="Fix", references=["appunti.md"]))
    with pytest.raises(ValidationError):
        data_service.create_reference("My App", NoteType.AGENT_TASK, Reference(title="x"))
    task = data_service.create_agent_task("My App", AgentTask(title="Fix"))
    with pytest.raises(ValidationError):
        data_service.save_reference("My App", task, Reference(title="x"))
    with pytest.raises(NotFoundError):
        data_service.save_reference("My App", "code-reference-manca.md", Reference(title="x"))
