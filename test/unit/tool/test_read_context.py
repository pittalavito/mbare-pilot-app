"""read_context: the markdown files of the project's context/ folder
(project/<slug>/context), nothing else."""

import pytest

from fakes import as_dict
from models.domain.project import Project, ProjectSource
from tool.context import ToolContext
from tool.list.project.read_context import READ_CONTEXT


@pytest.fixture
def project_data(project_data_service, project_store):
    project_store.save(Project(name="My App", source=ProjectSource.FOLDER, root_path="/code/app"))
    return project_data_service


def _read(project_data, project="My App"):
    return as_dict(READ_CONTEXT.build(ToolContext(project, git=None, project_data=project_data)).func())


def test_reads_the_markdown_files_of_the_context_folder(project_data, project_file_store):
    project_file_store.save("my-app/context/context.md", b"Gestionale navi")
    project_file_store.save("my-app/context/linee-guida.md", b"Breve.")
    project_file_store.save("my-app/context/schema.png", b"\x89PNG")
    project_file_store.save("my-app/notes/altro.md", b"nota")

    assert _read(project_data) == {"files": {"context.md": "Gestionale navi", "linee-guida.md": "Breve."}}


def test_errors_without_files_or_project(project_data):
    assert "non ha file di contesto" in _read(project_data)["error"]
    assert "fuori da un progetto" in _read(project_data, project=None)["error"]
    assert "non trovato" in _read(project_data, project="Nessuno")["error"]
