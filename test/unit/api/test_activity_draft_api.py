"""«📎 Da riferimenti»: the secretary (one structured call, fake model)
proposes a new activity reading only the titles of the chosen references and
context pieces; nothing is created."""
import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.container import Container
from fakes import FakeStructuredClient as FakeClient
from models.domain.activity_draft import DraftAnswer
from models.domain.project import Project, ProjectSource
from service.activity_draft_service import MAX_TITLES, model_input


@pytest.fixture
def model():
    return FakeClient(DraftAnswer(title=" Login con OTP ", description="Aggiungere l'OTP al login.", items=["Analisi", " ", "Sviluppo"]))


@pytest.fixture
def client(stores, monkeypatch, project_store, tmp_path, model, default_chatbots):
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path=str(tmp_path)))
    container = Container(stores=stores)
    monkeypatch.setattr(container.chat_service, "get_client", lambda key: model)
    with TestClient(create_app(container)) as client:
        client.put("/projects/acme/notes/context-reference-spec-login.md", json={"content": "segreto: il corpo non va al modello"})
        yield client


def test_a_proposal_from_references_and_context(client, model):
    references = ["context-reference-spec-login", "context-reference-spec-login.md"]
    draft = client.post("/projects/acme/activities/draft", json={"references": references, "context": ["Architettura · Login", " "]}).json()

    assert (draft["title"], draft["items"]) == ("Login con OTP", ["Analisi", "Sviluppo"])
    assert draft["references"] == ["context-reference-spec-login.md"]
    [call] = model.calls
    assert call["system_prompt"].startswith("Dai titoli dei riferimenti")
    assert "spec login" in call["input"] and "Architettura · Login" in call["input"]
    assert "segreto" not in call["input"]  # only the titles
    assert client.get("/projects/acme/activities").json() == []  # nothing created


def test_only_context_and_an_empty_title(client, model):
    model.answer = DraftAnswer(title=" ", items=[])

    draft = client.post("/projects/acme/activities/draft", json={"context": ["Architettura"]}).json()

    assert (draft["title"], draft["references"]) == ("Architettura", [])


def test_nothing_chosen_is_a_400(client):
    assert client.post("/projects/acme/activities/draft", json={"references": [" "], "context": []}).status_code == 400


def test_a_note_that_is_not_a_reference_is_a_400(client):
    client.put("/projects/acme/notes/appunti.md", json={"content": "x"})

    assert client.post("/projects/acme/activities/draft", json={"references": ["appunti.md"]}).status_code == 400


def test_a_failing_model_is_a_502(client, model):
    model.error = RuntimeError("giù")

    assert client.post("/projects/acme/activities/draft", json={"context": ["Architettura"]}).status_code == 502


def test_an_empty_structured_answer_is_a_502(client, model, monkeypatch):
    monkeypatch.setattr(model, "structured_response", lambda **kwargs: type("R", (), {"structured_data": []})())

    assert client.post("/projects/acme/activities/draft", json={"context": ["Architettura"]}).status_code == 502


def test_without_the_agent_is_a_404(client, stores):
    stores.agents.delete_config("bozza-attivita")

    assert client.post("/projects/acme/activities/draft", json={"context": ["Architettura"]}).status_code == 404


def test_the_run_is_the_agent_s(client, stores):
    draft = client.post("/projects/acme/activities/draft", json={"context": ["Architettura"]}).json()

    [run] = [run for run in stores.runs.list_runs() if run.run_id == draft["run_id"]]
    assert (run.origin, run.config_name, run.model) == ("draft", "bozza-attivita", "google/gemini-2.5-pro")


def test_model_input_keeps_the_call_small():
    text = model_input([f"R{i}" for i in range(MAX_TITLES + 5)], ["x" * 500])

    assert text.count("\n- R") == MAX_TITLES and "x" * 201 not in text
    assert model_input([], ["C"]) == "Contesto del progetto:\n- C"


def test_a_proposal_from_the_description_alone(client, model):
    model.answer = DraftAnswer(title=" ", items=[])

    draft = client.post("/projects/acme/activities/draft", json={"description": " Aggiungere l'OTP al login\nper tutti "}).json()

    assert draft["title"] == "Aggiungere l'OTP al login"
    [call] = model.calls
    assert call["input"].startswith("Cosa voglio fare:\nAggiungere l'OTP")


def test_model_input_puts_the_description_first():
    text = model_input(["R"], [], "y" * 3000)

    assert text.startswith("Cosa voglio fare:\n") and "\nRiferimenti:\n- R" in text and "y" * 2001 not in text
