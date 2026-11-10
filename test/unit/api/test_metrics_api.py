"""The Metriche page over the API: the numbers, the evaluations queued for the worker, the reports."""
import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.container import Container
from fakes import make_run_record


@pytest.fixture
def container(stores, tmp_path):
    container = Container(stores=stores)
    container.evaluation_service._reports = tmp_path / "evaluations"
    return container


@pytest.fixture
def client(container):
    with TestClient(create_app(container)) as client:
        yield client


def test_the_numbers(client, run_store):
    run_store.save(make_run_record("r1").model_copy(update={"config_name": "chatbot/Segretario"}))

    body = client.get("/observability/metrics", params={"days": 7}).json()

    assert body["days"] == 7 and body["project_name"] is None
    assert [(agent["name"], agent["calls"]) for agent in body["agents"]] == [("chatbot/Segretario", 1)]
    assert body["copilot"] == [] and body["wip"]["acceptance_rate"] is None


def test_an_evaluation_is_queued_run_by_the_worker_and_its_report_downloaded(client, container):
    assert client.post("/observability/evaluations", json={"kind": "wip", "models": []}).status_code == 400
    queued = client.post("/observability/evaluations", json={"kind": "rag", "embedders": ["hashing"]})
    assert queued.status_code == 201 and queued.json()["status"] == "queued"

    done = container.evaluation_service.run_next()  # what the worker does

    listed = client.get("/observability/evaluations").json()
    assert [run["status"] for run in listed["runs"]] == ["done"] and [report["name"] for report in listed["reports"]] == [done.report]
    markdown = client.get(f"/observability/evaluations/reports/{done.report}")
    assert markdown.headers["content-type"].startswith("text/markdown") and markdown.text.startswith("# Valutazione della ricerca")
    assert client.get(f"/observability/evaluations/reports/{done.report}", params={"format": "json"}).json()[0]["embedder"] == "hashing-512"
    assert client.get("/observability/evaluations/reports/rag-20000101-000000").status_code == 404
