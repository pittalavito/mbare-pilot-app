"""«Elabora WIP» over the API: state, preview, process (fake model), apply."""
import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.container import Container
from fakes import FakeStructuredClient as FakeClient
from models.domain.project import Project, ProjectSource
from models.domain.wip import ProposalKind, WipAnswer, WipAnswerProposal


@pytest.fixture
def model():
    return FakeClient(WipAnswer(proposals=[WipAnswerProposal(kind=ProposalKind.NEW_ACTIVITY, source="login lento", title="Login lento")]))


@pytest.fixture
def client(stores, monkeypatch, project_store, tmp_path, model):
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path=str(tmp_path)))
    container = Container(stores=stores)  # seeds the default chatbots: the secretary too
    monkeypatch.setattr(container.chat_service, "get_client", lambda key: model)
    with TestClient(create_app(container)) as client:
        yield client


def test_the_whole_flow(client, model):
    assert client.get("/projects/acme/wip").json() == {"content": "", "pending_words": 0}
    assert client.post("/projects/acme/wip/preview", json={}).status_code == 400  # nothing to process
    client.put("/projects/acme/notes/wip.md", json={"content": "il login è lento, scrivere a ada@acme.it"})

    preview = client.post("/projects/acme/wip/preview", json={"paragraphs": None}).json()
    assert preview["text"].endswith("il login è lento, scrivere a MAIL_1")
    assert preview["spans"][-1] == {"start": len(preview["text"]) - 6, "end": len(preview["text"]), "alias": "MAIL_1", "origin": "auto"}

    result = client.post("/projects/acme/wip/process", json={}).json()
    assert [proposal["title"] for proposal in result["proposals"]] == ["Login lento"]
    assert "ada@acme.it" not in model.calls[0]["input"]

    applied = client.post("/projects/acme/wip/apply", json={
        "run_id": result["run_id"], "choices": [{"proposal": result["proposals"][0], "edited": False}],
    }).json()
    assert applied == {"applied": ["Nuova attività «Login lento» (attivita-login-lento.md)"], "skipped": []}
    assert "—— elaborato il" in client.get("/projects/acme/wip").json()["content"]
    assert client.get("/projects/acme/wip").json()["pending_words"] == 0
    [run] = client.get("/projects/acme/wip/runs").json()
    assert (run["proposed"], run["accepted"]) == (1, 1)

    again = client.post("/projects/acme/wip/apply", json={"run_id": result["run_id"], "choices": [{"proposal": result["proposals"][0]}]})
    assert again.status_code == 409


def test_a_failing_model_is_a_502(client, model):
    client.put("/projects/acme/notes/wip.md", json={"content": "qualcosa"})
    model.error = RuntimeError("giù")

    assert client.post("/projects/acme/wip/process", json={}).status_code == 502
