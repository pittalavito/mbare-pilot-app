"""POST /projects/{project}/code-todos: the todoMbarePilot comments of the code
gathered into one code reference, from the UI, without an agent."""
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.container import Container
from models.domain.project import Project, ProjectSource

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


@pytest.fixture
def client(stores, tmp_path, project_store):
    repo = tmp_path / "acme"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    (repo / "main.py").write_text("# todoMbarePilot{Rifai il login}\n", encoding="utf-8")
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path=str(repo)))
    with TestClient(create_app(Container(stores=stores))) as client:
        yield client


def test_the_scan_writes_the_note_and_answers_with_counts(client):
    scan = client.post("/projects/acme/code-todos")

    assert scan.status_code == 200
    assert scan.json() == {"note": "code-reference-todo-mbare-pilot.md", "created": True, "files": 1, "comments": 1}
    [reference] = client.get("/projects/acme/references").json()
    assert reference["name"] == "code-reference-todo-mbare-pilot.md" and "riga 1: Rifai il login" in reference["content"]
    assert client.post("/projects/acme/code-todos").json()["created"] is False


def test_a_note_with_that_name_written_by_hand_is_a_conflict(client):
    client.post("/projects/acme/references", json={"kind": "code_reference", "title": "TODO Mbare Pilot", "content": "mio"})

    assert client.post("/projects/acme/code-todos").status_code == 409
    assert client.post("/projects/manca/code-todos").status_code == 404
