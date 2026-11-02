"""The todoMbarePilot{...} comments of a project's code, on real git
repositories: which files are read, and the one code reference they become."""
import shutil
import subprocess
from datetime import datetime

import pytest

from core.error import ConflictError
from domain.project import code_todos
from models.domain.code_todo import CodeTodo
from models.domain.note import NoteType, Reference
from models.domain.project import Project, ProjectSource
from service.code_todo_service import MAX_FILE_BYTES, CodeTodoService

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

NOTE = "code-reference-todo-mbare-pilot.md"
WHEN = datetime(2026, 11, 2, 14, 30)


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _repo(path, files: dict[str, str | bytes], ignore: str = "") -> None:
    path.mkdir(parents=True)
    _git(path, "init", "-q")
    for name, content in files.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    if ignore:
        (path / ".gitignore").write_text(ignore, encoding="utf-8")


@pytest.fixture
def project(tmp_path, project_store):
    """Project ``acme``: repositories ``api`` and ``web``, with comments in tracked, new, ignored and odd files."""
    root = tmp_path / "acme"
    _repo(root / "api", {
        "src/login.py": "def login():\n    # todoMbarePilot{Rifattorizza il controllo password}\n    pass  # todoMbarePilot{Gestire   il timeout}\n",
        "src/vuoto.py": "# todoMbarePilot{}\n# todoMbarePilot{  }\nx = 1\n",
        "README.md": "nessun commento qui\n",
        "nuovo.py": "// todoMbarePilot{File nuovo, non ancora aggiunto}\n",  # untracked, not ignored: read
        "build/out.js": "// todoMbarePilot{Generato}\n",  # ignored
        "logo.png": b"\x89PNG\0\0todoMbarePilot{binario}",
        "latin1.txt": "todoMbarePilot{caffè}".encode("latin-1"),
        "grande.txt": "todoMbarePilot{troppo grande}\n" + "x" * MAX_FILE_BYTES,
        "mbare-pilot/agent-task-x/task.md": "todoMbarePilot{la cartella del task per Copilot}\n",
    }, ignore="build/\n")
    _git(root / "api", "add", "src", "README.md", "logo.png", "latin1.txt", "grande.txt", "mbare-pilot", ".gitignore")
    _repo(root / "web", {"src/App.tsx": "<!-- todoMbarePilot{Togliere il mock} -->\n{/* todoMbarePilot{Uno} todoMbarePilot{Due} */}\n"})
    _git(root / "web", "add", ".")
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path=str(root)))
    return root


@pytest.fixture
def service(git_service, project_data_service):
    return CodeTodoService(git_service, project_data_service, clock=lambda: WHEN)


def test_the_scan_reads_the_files_git_knows_and_skips_the_others(service, project):
    assert service.scan("acme") == {
        "api/nuovo.py": [CodeTodo(line=1, description="File nuovo, non ancora aggiunto")],
        "api/src/login.py": [
            CodeTodo(line=2, description="Rifattorizza il controllo password"),
            CodeTodo(line=3, description="Gestire il timeout"),
        ],
        "web/src/App.tsx": [
            CodeTodo(line=1, description="Togliere il mock"),
            CodeTodo(line=2, description="Uno"), CodeTodo(line=2, description="Due"),
        ],
    }


def test_a_deleted_tracked_file_is_skipped(service, project):
    (project / "api" / "src" / "login.py").unlink()  # still in git's index

    assert "api/src/login.py" not in service.scan("acme")


def test_the_project_folder_itself_can_be_the_repository(tmp_path, project_store, git_service, project_data_service):
    _repo(tmp_path / "solo", {"main.go": "// todoMbarePilot{Nella radice}\n"})
    project_store.save(Project(name="solo", source=ProjectSource.FOLDER, root_path=str(tmp_path / "solo")))

    assert CodeTodoService(git_service, project_data_service).scan("solo") == {"main.go": [CodeTodo(line=1, description="Nella radice")]}


def test_save_writes_one_note_grouped_by_file_and_rewrites_it(service, project, project_data_service):
    first = service.save("acme")

    assert (first.note, first.created, first.files, first.comments) == (NOTE, True, 3, 6)
    kind, note = project_data_service.reference("acme", NOTE)
    assert (kind, note.title, note.source) == (NoteType.CODE_REFERENCE, "TODO Mbare Pilot", "todoMbarePilot")
    assert note.content == (
        "Commenti `todoMbarePilot{…}` trovati nel codice il 2026-11-02 14:30: 6 in 3 file.\n\n"
        "### api/nuovo.py\n- riga 1: File nuovo, non ancora aggiunto\n\n"
        "### api/src/login.py\n- riga 2: Rifattorizza il controllo password\n- riga 3: Gestire il timeout\n\n"
        "### web/src/App.tsx\n- riga 1: Togliere il mock\n- riga 2: Uno\n- riga 2: Due"
    )

    (project / "api" / "nuovo.py").unlink()
    second = service.save("acme")
    assert (second.note, second.created, second.files, second.comments) == (NOTE, False, 2, 5)
    assert "nuovo.py" not in project_data_service.reference("acme", NOTE)[1].content


def test_nothing_found_creates_no_note_but_empties_an_existing_one(tmp_path, project_store, git_service, project_data_service):
    _repo(tmp_path / "pulito", {"a.py": "x = 1\n"})
    project_store.save(Project(name="pulito", source=ProjectSource.FOLDER, root_path=str(tmp_path / "pulito")))
    service = CodeTodoService(git_service, project_data_service, clock=lambda: WHEN)

    nothing = service.save("pulito")
    assert (nothing.note, nothing.created, nothing.files, nothing.comments) == (None, False, 0, 0)
    assert project_data_service.references("pulito") == []

    (tmp_path / "pulito" / "a.py").write_text("# todoMbarePilot{Uno}\n", encoding="utf-8")
    assert service.save("pulito").created
    (tmp_path / "pulito" / "a.py").write_text("x = 1\n", encoding="utf-8")
    emptied = service.save("pulito")

    assert (emptied.note, emptied.comments) == (NOTE, 0)
    assert project_data_service.reference("pulito", NOTE)[1].content == (
        "Nessun commento `todoMbarePilot{…}` trovato nel codice (scansione del 2026-11-02 14:30)."
    )


def test_a_note_with_that_name_written_by_hand_is_left_alone(service, project, project_data_service):
    project_data_service.create_reference("acme", NoteType.CODE_REFERENCE, Reference(title="TODO Mbare Pilot", content="mio"))

    with pytest.raises(ConflictError, match="scritto a mano"):
        service.save("acme")
    assert project_data_service.reference("acme", NOTE)[1].content == "mio"


def test_the_links_to_the_note_survive_a_new_scan(service, project, project_data_service):
    from models.domain.note import AgentTask

    service.save("acme")
    task = project_data_service.create_agent_task("acme", AgentTask(title="Todo del codice", references=[NOTE]))
    service.save("acme")

    assert project_data_service.agent_task("acme", task).references == [NOTE]


@pytest.mark.parametrize("line, found", [
    ("// todoMbarePilot{Rifai}", ["Rifai"]),
    ("# todoMbarePilot{ spazi   in   mezzo }", ["spazi in mezzo"]),
    ("todomBarePilot{maiuscole diverse}", []),
    ("todoMbarePilot{senza chiusura", []),
    ("todoMbarePilot {spazio prima della graffa}", []),
    ("a todoMbarePilot{uno} b todoMbarePilot{due}", ["uno", "due"]),
])
def test_the_marker(line, found):
    assert [todo.description for todo in code_todos.find(line)] == found


def test_a_file_that_cannot_be_read_is_skipped(service, project, monkeypatch):
    from pathlib import Path

    real = Path.read_bytes

    def read_bytes(path):
        if path.name == "login.py":
            raise PermissionError("negato")
        return real(path)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)

    assert "api/src/login.py" not in service.scan("acme") and "web/src/App.tsx" in service.scan("acme")
