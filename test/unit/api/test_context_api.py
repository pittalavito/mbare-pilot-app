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


