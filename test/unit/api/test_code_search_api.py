"""POST /projects/{project}/code-search and /code-search/reference."""
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
    (repo / "main.py").write_text("x = 1\n# OrderService qui\n", encoding="utf-8")
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path=str(repo)))
    with TestClient(create_app(Container(stores=stores))) as client:
        yield client


def test_search_and_broken_regex(client):
    found = client.post("/projects/acme/code-search", json={"query": "OrderService"})

    assert found.status_code == 200
    assert found.json() == {"matches": [{"path": "main.py", "line": 2, "text": "# OrderService qui"}], "total": 1, "files": 1, "truncated": False}
    assert client.post("/projects/acme/code-search", json={"query": "(", "regex": True}).status_code == 400
    assert client.post("/projects/acme/code-search", json={"query": ""}).status_code == 422


def test_save_links_to_the_task_and_conflicts_with_a_hand_written_reference(client):
    task = client.post("/projects/acme/agent-tasks", json={"title": "Login"}).json()["name"]
    saved = client.post("/projects/acme/code-search/reference", json={"query": "OrderService", "title": "Ordini", "task": task})

    assert saved.json() == {"note": "code-reference-ordini.md", "created": True, "total": 1}
    reference = next(r for r in client.get("/projects/acme/references").json() if r["name"] == "code-reference-ordini.md")
    assert "`main.py:2`" in reference["content"] and task in reference["linked_from"]
    assert client.post("/projects/acme/code-search/reference", json={"query": "x", "title": "Ordini"}).json()["created"] is False
    client.post("/projects/acme/references", json={"kind": "code_reference", "title": "Mia", "content": "mio"})
    assert client.post("/projects/acme/code-search/reference", json={"query": "x", "title": "Mia"}).status_code == 409
