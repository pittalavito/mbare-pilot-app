import pytest

from core.error import ConflictError, NotFoundError, ValidationError
from domain.project.folder_browser import FolderBrowser
from models.domain.project import ProjectSource
from service.project_service import ProjectService


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "workspace"
    (root / "existing-app").mkdir(parents=True)
    (root / "existing-app" / "main.py").write_text("print('hi')", encoding="utf-8")
    return root


@pytest.fixture
def project_service(store_service, root):
    return ProjectService(store_service, FolderBrowser([root]))


def test_open_existing_folder(project_service, root):
    project = project_service.open_folder("App", "desc", root / "existing-app")

    assert project.source == ProjectSource.FOLDER
    assert project.root_path == str((root / "existing-app").resolve())
    assert [p.name for p in project_service.list_projects(ProjectSource.FOLDER)] == ["App"]


def test_open_folder_outside_roots_rejected(project_service, tmp_path):
    (tmp_path / "elsewhere").mkdir()
    with pytest.raises(ValidationError):
        project_service.open_folder("X", "", tmp_path / "elsewhere")
    assert project_service.list_projects() == []


def test_same_name_or_same_folder_conflicts(project_service, root):
    project_service.open_folder("App", "", root / "existing-app")

    with pytest.raises(ConflictError):
        project_service.open_folder("App", "", root)
    with pytest.raises(ConflictError, match="App"):
        project_service.open_folder("Other", "", root / "existing-app")


def test_create_from_scratch_creates_the_folder(project_service, root):
    project = project_service.create_from_scratch("New", "", root, "new-app")

    assert project.source == ProjectSource.SCRATCH
    assert (root / "new-app").is_dir()


def test_create_from_scratch_conflict_creates_nothing(project_service, root):
    project_service.open_folder("App", "", root / "existing-app")

    with pytest.raises(ConflictError):
        project_service.create_from_scratch("App", "", root, "never-created")
    assert not (root / "never-created").exists()


def test_create_from_scratch_existing_folder_rejected(project_service, root):
    with pytest.raises(ValidationError):
        project_service.create_from_scratch("New", "", root, "existing-app")
    assert project_service.list_projects() == []


def test_remove_keeps_folder_and_missing_folder_is_detected(project_service, root):
    project = project_service.create_from_scratch("New", "", root, "new-app")

    (root / "new-app").rmdir()
    assert project_service.folder_exists(project) is False

    assert project_service.remove("New") is True
    with pytest.raises(NotFoundError):
        project_service.get_project("New")


def test_remove_does_not_delete_folder(project_service, root):
    project_service.open_folder("App", "", root / "existing-app")

    project_service.remove("App")
    assert (root / "existing-app" / "main.py").exists()
