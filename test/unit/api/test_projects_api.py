"""Projects and folders API over the in-memory store (no Postgres, no Redis)."""
import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.container import Container
from domain.project.folder_browser import FolderBrowser
from service.project_service import ProjectService


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "workspace"
    (root / "existing-app" / "src").mkdir(parents=True)
    (root / "other").mkdir()
    return root


@pytest.fixture
def client(stores, store_service, root):
    container = Container(stores=stores)
    container.project_service = ProjectService(store_service, FolderBrowser([root]))
    with TestClient(create_app(container)) as client:
        yield client


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_open_folder_uses_the_folder_name_by_default(client, root):
    response = client.post("/projects/open-folder", json={"folder": str(root / "existing-app")})

    assert response.status_code == 201
    body = response.json()
    assert (body["name"], body["source"], body["folder_exists"]) == ("existing-app", "folder", True)
    assert [p["name"] for p in client.get("/projects").json()] == ["existing-app"]


def test_create_from_scratch_creates_the_folder(client, root):
    response = client.post("/projects/from-scratch", json={"name": "Nuova App", "parent": str(root)})

    assert response.status_code == 201
    assert (root / "Nuova App").is_dir()
    assert response.json()["source"] == "scratch"


def test_get_update_and_remove(client, root):
    client.post("/projects/open-folder", json={"folder": str(root / "existing-app"), "name": "Mio Progetto"})

    assert client.get("/projects/Mio Progetto").json()["name"] == "Mio Progetto"
    updated = client.patch("/projects/Mio Progetto", json={
        "description": "nuova", "embedding_model": "ollama/nomic-embed-text",
    }).json()
    assert (updated["description"], updated["embedding_model"]) == ("nuova", "ollama/nomic-embed-text")

    assert client.delete("/projects/Mio Progetto").status_code == 204
    assert client.get("/projects/Mio Progetto").status_code == 404
    assert (root / "existing-app").is_dir()


@pytest.mark.parametrize("call, status", [
    (lambda c, r: c.get("/projects/ghost"), 404),
    (lambda c, r: c.delete("/projects/ghost"), 404),
    (lambda c, r: c.post("/projects/open-folder", json={"folder": str(r.parent)}), 400),
    (lambda c, r: c.post("/projects/from-scratch", json={"name": "x", "parent": str(r), "folder_name": "other"}), 400),
    (lambda c, r: c.patch("/projects/ghost", json={"description": "", "embedding_model": "bad"}), 422),
])
def test_errors_become_http_status(client, root, call, status):
    response = call(client, root)

    assert response.status_code == status
    assert response.json()["detail"]


def test_same_folder_twice_conflicts(client, root):
    client.post("/projects/open-folder", json={"folder": str(root / "existing-app")})

    response = client.post("/projects/open-folder", json={"folder": str(root / "existing-app"), "name": "altro"})
    assert response.status_code == 409


def test_options(client):
    assert "openai/text-embedding-3-small" in client.get("/projects/options").json()["embedding_models"]


def test_folder_picker(client, root):
    assert client.get("/folders/roots").json() == {"roots": [str(root.resolve())]}

    top = client.get("/folders").json()
    assert (top["path"], top["parent"]) == (str(root.resolve()), None)
    assert [f["name"] for f in top["subfolders"]] == ["existing-app", "other"]

    inner = client.get("/folders", params={"path": top["subfolders"][0]["path"]}).json()
    assert inner["parent"] == str(root.resolve())
    assert [f["name"] for f in inner["subfolders"]] == ["src"]

    assert client.get("/folders", params={"path": str(root.parent)}).status_code == 400


@pytest.mark.parametrize("name", ["a/b", "a\\b"])
def test_names_with_slashes_are_rejected(client, root, name):
    response = client.post("/projects/open-folder", json={"folder": str(root / "existing-app"), "name": name})

    assert response.status_code == 400
