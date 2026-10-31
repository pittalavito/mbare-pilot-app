"""The definitions API: preview what the files define, sync all or only the chosen elements."""
import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.container import Container
from models.domain.project import Project, ProjectSource

AUTOMATIONS = """automations:
  - {name: Uno, steps: [{name: S, function: git_status}]}
  - {name: Due, steps: [{name: S, function: git_status}]}
"""


@pytest.fixture
def client(stores, store_service, tmp_path, project_store):
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path=str(tmp_path)))
    store_service.save_definition("global-agent.yml", "")
    store_service.save_definition("project/acme/automation.yml", AUTOMATIONS)
    with TestClient(create_app(Container(stores=stores))) as client:
        yield client


def test_preview_then_sync_only_the_chosen_element(client):
    preview = client.get("/projects/acme/definitions").json()
    assert [(entry["name"], entry["state"]) for entry in preview] == [("Uno", "new"), ("Due", "new")]

    chosen = [{key: preview[1][key] for key in ("kind", "file", "name")}]
    report = client.post("/projects/acme/definitions/sync", json={"only": chosen}).json()

    assert [(item["name"], item["outcome"]) for item in report["items"]] == [("Due", "created")]
    assert [(entry["name"], entry["state"]) for entry in client.get("/projects/acme/definitions").json()] == [("Uno", "new"), ("Due", "exists")]


def test_sync_without_a_body_applies_everything(client):
    report = client.post("/projects/acme/definitions/sync").json()

    assert [(item["name"], item["outcome"]) for item in report["items"]] == [("Uno", "created"), ("Due", "created")]
    assert client.get("/projects/nessuno/definitions").status_code == 404
