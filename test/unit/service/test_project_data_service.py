import pytest

from core.error import ConflictError, NotFoundError, ValidationError
from domain.project.data_paths import data_file_name, note_file_name, project_slug
from domain.project.folder_browser import FolderBrowser
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
