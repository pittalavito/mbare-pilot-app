"""The project's context over the API: documents (saving indexes them), the
index, «Reindicizza tutto», the search; a done activity with «Imparato»."""
import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.container import Container
from models.domain.project import Project, ProjectSource


@pytest.fixture
def client(stores, project_store, tmp_path):
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path=str(tmp_path)))
    with TestClient(create_app(Container(stores=stores))) as client:
        yield client


def test_documents_are_indexed_when_saved_and_searched(client):
    assert client.get("/projects/acme/context").json() == []
    saved = client.put("/projects/acme/context/architettura", json={"content": "# Architettura\n\n## Database\nPostgreSQL con Flyway."})
    assert saved.json() == {"name": "architettura.md", "index_error": None}
    assert [item["name"] for item in client.get("/projects/acme/context").json()] == ["architettura.md"]
    assert client.get("/projects/acme/context/architettura.md").json()["content"].startswith("# Architettura")

    assert client.get("/projects/acme/context-index").json() == {"documents": 1, "pieces": 1, "embedder": "hashing-512", "error": None}
    [hit] = client.post("/projects/acme/context-index/search", json={"question": "Dove sono le migrazioni Flyway?"}).json()
    assert (hit["path"], hit["section"]) == ("context/architettura.md", "Database")
    assert client.post("/projects/acme/context-index/reindex").json()["documents"] == 1

    assert client.delete("/projects/acme/context/architettura.md").status_code == 204
    assert client.get("/projects/acme/context-index").json()["documents"] == 0
    assert client.delete("/projects/acme/context/architettura.md").status_code == 404


def test_a_save_reports_an_index_error_but_keeps_the_document(client, config):
    config.rag_embedder = "sconosciuto"

    saved = client.put("/projects/acme/context/doc", json={"content": "# Doc"}).json()

    assert "Embedder sconosciuto" in saved["index_error"]
    assert client.get("/projects/acme/context/doc.md").status_code == 200
    assert client.post("/projects/acme/context-index/reindex").status_code == 400


def test_a_done_activity_with_imparato_enters_the_context(client):
    name = client.post("/projects/acme/activities", json={"title": "Rilascio"}).json()["name"]
    body = {"title": "Rilascio", "status": "done", "learned": "Le note di rilascio vanno scritte prima del tag."}

    saved = client.put(f"/projects/acme/activities/{name}", json=body).json()

    assert saved["learned"] == body["learned"]
    [hit, *_] = client.post("/projects/acme/context-index/search", json={"question": "Quando scrivo le note di rilascio?"}).json()
    assert (hit["path"], hit["section"]) == (f"notes/{name}", "Imparato")
