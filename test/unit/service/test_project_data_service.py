import pytest

from core.error import ConflictError, NotFoundError, ValidationError
from domain.project.data_paths import data_file_name, note_file_name, project_slug
from domain.project.folder_browser import FolderBrowser
from models.domain.note import Activity, ActivityStatus, AgentTask, ChecklistItem, NoteType, TaskStatus, TodoItem, TodoPriority
from models.domain.project import Project, ProjectDataKind, ProjectSource
from service.project_service import ProjectService


@pytest.fixture
def data_service(files_repository, project_data_service, project_store):
    project_store.save(Project(name="My App", source=ProjectSource.FOLDER, root_path="/code/my-app"))
    return project_data_service


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
    data_service.create_activity("My App", Activity(title="Rilascio", items=[TodoItem(text="tag", priority=TodoPriority.LOW)]))
    data_service.save_note("My App", "decisioni", "# Decisioni")

    assert name == "agent-task-refactor-login.md"
    assert (files_repository.root / "my-app" / "notes" / name).read_text(encoding="utf-8").startswith("# Refactor login\n\nStato: creato\nTipo: sviluppo\n")
    assert {note.name: note.note_type for note in data_service.list_notes("My App")} == {
        "agent-task-refactor-login.md": NoteType.AGENT_TASK, "decisioni.md": NoteType.GENERIC, "attivita-rilascio.md": NoteType.ACTIVITY,
    }
    [(_, activity)] = data_service.activities("My App")
    assert activity.items[0].priority == TodoPriority.LOW

    data_service.save_agent_task("My App", name, AgentTask(title="Refactor login (v2)", status=TaskStatus.DONE))
    assert data_service.agent_tasks("My App") == [(name, AgentTask(title="Refactor login (v2)", status=TaskStatus.DONE))]


def test_typed_notes_refuse_duplicates_other_types_and_missing_ones(data_service):
    data_service.create_activity("My App", Activity(title="Rilascio"))

    with pytest.raises(ConflictError):
        data_service.create_activity("My App", Activity(title="rilascio!"))
    with pytest.raises(ValidationError):
        data_service.save_agent_task("My App", "attivita-rilascio.md", AgentTask(title="x"))
    with pytest.raises(NotFoundError):
        data_service.save_activity("My App", "attivita-altro.md", Activity(title="x"))
    with pytest.raises(ValidationError, match="non è un'attività"):
        data_service.activity("My App", "agent-task-x.md")
    with pytest.raises(ValidationError, match="un'attività collega solo agent-task"):
        data_service.create_activity("My App", Activity(title="Altra", agent_tasks=["appunti.md"]))


def test_unknown_project(data_service):
    with pytest.raises(NotFoundError):
        data_service.list_notes("ghost")


def test_projects_with_the_same_slug_conflict(tmp_path, mask_store, project_store):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    projects = ProjectService(project_store, mask_store, FolderBrowser([tmp_path]))
    projects.open_folder("My App", "", tmp_path / "a")

    with pytest.raises(ConflictError):
        projects.open_folder("my-app", "", tmp_path / "b")


# ---------------------------------------------------------------- references

def test_references_are_linked_to_tasks_and_activities_many_to_many(data_service):
    from models.domain.note import Reference

    code = data_service.create_reference("My App", NoteType.CODE_REFERENCE, Reference(title="Login", repository="api", path="a.py"))
    context = data_service.create_reference("My App", NoteType.CONTEXT_REFERENCE, Reference(title="Procedura", source="jira"))
    task = data_service.create_agent_task("My App", AgentTask(title="Fix", references=[code, context]))
    todo = data_service.create_activity("My App", Activity(title="Rilascio", references=[context]))

    assert (code, context) == ("code-reference-login.md", "context-reference-procedura.md")
    assert [(name, kind) for name, kind, _ in data_service.references("My App")] == [(code, NoteType.CODE_REFERENCE), (context, NoteType.CONTEXT_REFERENCE)]
    assert data_service.reference("My App", code)[1].path == "a.py"
    assert data_service.linked_from("My App") == {code: [task], context: [task, todo]}

    data_service.save_reference("My App", context, Reference(title="Procedura v2"))
    assert data_service.reference("My App", context)[1].title == "Procedura v2"
    assert data_service.delete_reference("My App", context)
    assert data_service.agent_task("My App", task).references == [code]  # unlinked everywhere
    assert data_service.activities("My App")[0][1].references == []


def test_only_references_can_be_linked_and_saved_as_references(data_service):
    from models.domain.note import Reference

    with pytest.raises(ValidationError, match="non si può collegare come riferimento"):
        data_service.create_agent_task("My App", AgentTask(title="Fix", references=["attivita-x.md"]))
    with pytest.raises(ValidationError):
        data_service.create_reference("My App", NoteType.AGENT_TASK, Reference(title="x"))
    task = data_service.create_agent_task("My App", AgentTask(title="Fix"))
    with pytest.raises(ValidationError):
        data_service.save_reference("My App", task, Reference(title="x"))
    with pytest.raises(NotFoundError):
        data_service.save_reference("My App", "code-reference-manca.md", Reference(title="x"))


# ------------------------------------------------------------- activities

def test_agent_tasks_born_from_an_activity_are_linked_and_unlinked_when_deleted(data_service):
    activity = data_service.create_activity("My App", Activity(title="Rilascio"))
    first = data_service.create_agent_task("My App", AgentTask(title="Note di rilascio"))
    second = data_service.create_agent_task("My App", AgentTask(title="Tag"))

    data_service.link_agent_task("My App", activity, first)
    data_service.link_agent_task("My App", activity, "agent-task-tag")  # .md added
    data_service.link_agent_task("My App", activity, first)  # once

    assert data_service.activity("My App", activity).agent_tasks == [first, second]
    with pytest.raises(NotFoundError):
        data_service.link_agent_task("My App", activity, "agent-task-manca.md")
    with pytest.raises(ValidationError):
        data_service.link_agent_task("My App", activity, "appunti.md")

    assert data_service.delete_note("My App", first)
    assert data_service.activity("My App", activity).agent_tasks == [second]  # unlinked
    assert data_service.delete_note("My App", activity)
    assert data_service.agent_task("My App", second).title == "Tag"  # the task stays


def test_the_old_todo_lists_become_activities(data_service, files_repository):
    notes = files_repository.root / "my-app" / "notes"
    notes.mkdir(parents=True)
    (notes / "todo-list-rilascio.md").write_text(
        "# Rilascio v2\n\n- [x] Aggiornare  (alta, 2026-10-30)\n- [ ] Taggare\n\n## Riferimenti\n- context-reference-procedura.md\n",
        encoding="utf-8")
    (notes / "todo-list-fatta.md").write_text("# Fatta\n\n- [x] uno\n", encoding="utf-8")
    (notes / "todo-list-doppia.md").write_text("# Doppia vecchia\n", encoding="utf-8")
    (notes / "attivita-doppia.md").write_text("# Doppia\n\nStato: in corso\n", encoding="utf-8")

    assert data_service.migrate_todo_lists("My App") == 2

    activities = dict(data_service.activities("My App"))
    assert set(activities) == {"attivita-rilascio.md", "attivita-fatta.md", "attivita-doppia.md"}
    rilascio = activities["attivita-rilascio.md"]
    assert (rilascio.title, rilascio.status, rilascio.description) == ("Rilascio v2", ActivityStatus.TODO, "")
    assert [(item.text, item.done, item.priority) for item in rilascio.items] == [("Aggiornare", True, TodoPriority.HIGH), ("Taggare", False, None)]
    assert rilascio.references == ["context-reference-procedura.md"]
    assert activities["attivita-fatta.md"].status == ActivityStatus.DONE  # every item done
    assert activities["attivita-doppia.md"].title == "Doppia"  # the existing one is not touched...
    assert (notes / "todo-list-doppia.md").is_file()  # ...and the old one stays, logged
    assert not (notes / "todo-list-rilascio.md").exists()
    assert "Stato: da fare" in (notes / "attivita-rilascio.md").read_text(encoding="utf-8")  # written as an activity
    assert data_service.migrate_todo_lists("My App") == 0  # once


def test_a_link_from_jira_can_go_to_an_activity(data_service):
    from models.domain.note import Reference

    activity = data_service.create_activity("My App", Activity(title="Rilascio"))
    reference = data_service.create_reference("My App", NoteType.CONTEXT_REFERENCE, Reference(title="NAV-7"))

    data_service.link_reference("My App", reference, [activity])

    assert data_service.activity("My App", activity).references == [reference]
    with pytest.raises(ValidationError, match="né un'attività"):
        data_service.link_reference("My App", reference, ["appunti.md"])


def test_the_settings_saved_before_the_activities_still_read(project_store):
    from models.domain.project import Project, ProjectSource

    project = Project.model_validate({"name": "Vecchio", "source": ProjectSource.FOLDER, "root_path": "/x",
                                      "visible_note_types": ["generic", "todo_list"]})

    assert project.visible_note_types == [NoteType.GENERIC, NoteType.ACTIVITY]


# ------------------------------------------------------- notes and files

def test_notes_and_files_are_linked_as_references_and_unlinked_when_deleted(data_service):
    data_service.save_note("My App", "decisioni", "# Decisioni")
    data_service.save_file("My App", "specifiche.pdf", b"%PDF")
    activity = data_service.create_activity("My App", Activity(title="Rilascio", references=["decisioni.md", "files/specifiche.pdf"]))
    task = data_service.create_agent_task("My App", AgentTask(title="Fix", references=["decisioni.md", "files/specifiche.pdf"]))

    assert data_service.copilot_files("My App", task) == {
        "task.md": data_service.read_note("My App", task).encode("utf-8"), "decisioni.md": b"# Decisioni", "files/specifiche.pdf": b"%PDF",
    }
    for wrong in ("files/../x", "files/", "agent-task-fix.md"):
        with pytest.raises(ValidationError):
            data_service.save_agent_task("My App", task, AgentTask(title="Fix", references=[wrong]))

    assert data_service.delete_file("My App", "specifiche.pdf")
    assert data_service.agent_task("My App", task).references == ["decisioni.md"]
    assert data_service.activity("My App", activity).references == ["decisioni.md"]
    assert data_service.delete_note("My App", "decisioni")
    assert data_service.agent_task("My App", task).references == [] == data_service.activity("My App", activity).references


def test_the_dati_tab_can_hide_the_files(data_service, project_store):
    assert data_service.files_visible("My App") is True

    assert data_service.save_files_visible("My App", False) is False

    assert data_service.files_visible("My App") is False and project_store.get("My App").files_visible is False


# ----------------------------------------------------------------- settings

def test_the_dati_tab_shows_the_default_types_until_the_project_chooses(data_service, project_store):
    assert data_service.visible_note_types("My App") == [NoteType.GENERIC, NoteType.AGENT_TASK, NoteType.ACTIVITY]

    saved = data_service.save_visible_note_types("My App", [NoteType.CONTEXT_REFERENCE, NoteType.GENERIC, NoteType.GENERIC])

    assert saved == [NoteType.GENERIC, NoteType.CONTEXT_REFERENCE] == data_service.visible_note_types("My App")
    assert project_store.get("My App").description == ""  # the rest of the project untouched
    assert data_service.save_visible_note_types("My App", []) == []  # nothing shown is a choice too
    with pytest.raises(NotFoundError):
        data_service.visible_note_types("nessuno")
