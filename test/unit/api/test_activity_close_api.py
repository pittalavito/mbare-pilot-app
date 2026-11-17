"""Plan 18, the step «Chiudi»: the agent ``imparato`` proposes what to remember
(one structured call, fake model); closing writes it at the top of
context/imparato.md (indexed) and makes the activity done; reopening keeps it."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.container import Container
from fakes import FakeStructuredClient as FakeClient
from models.domain.activity_close import LearnedAnswer
from models.domain.note import Activity, TodoItem
from models.domain.project import Project, ProjectSource
from service.activity_close_service import LEARNED_HEADER, with_section


@pytest.fixture
def model():
    return FakeClient(LearnedAnswer(points=[" lib-auth prima dell'api ", " "]))


@pytest.fixture
def container(stores, monkeypatch, project_store, tmp_path, model, default_chatbots):
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path=str(tmp_path)))
    container = Container(stores=stores)
    monkeypatch.setattr(container.chat_service, "get_client", lambda key: model)
    return container


@pytest.fixture
def client(container):
    with TestClient(create_app(container)) as client:
        yield client


@pytest.fixture
def activity(container):
    return container.project_data_service.create_activity("acme", Activity(title="Login con OTP", description="SMS", items=[TodoItem(text="a")]))


def test_the_proposal_reads_the_activity_and_its_tasks(client, model, activity, stores):
    base = f"/projects/acme/activities/{activity}"
    client.post(f"{base}/plan/confirm", json={"choices": [{"title": "Libreria", "type": "development"}]})

    draft = client.post(f"{base}/learned").json()

    assert draft["points"] == ["lib-auth prima dell'api"]
    [call] = model.calls
    assert call["system_prompt"].startswith("Dall'attività finita") and "Attività: Login con OTP" in call["input"]
    assert "- Libreria (development, todo)" in call["input"]
    [run] = [run for run in stores.runs.list_runs() if run.run_id == draft["run_id"]]
    assert (run.origin, run.config_name) == ("learned", "imparato")


def test_a_failing_model_is_a_502(client, model, activity):
    model.error = RuntimeError("giù")

    assert client.post(f"/projects/acme/activities/{activity}/learned").status_code == 502


def test_closing_writes_at_the_top_of_imparato_and_reopening_keeps_it(client, container, activity, stores):
    base = f"/projects/acme/activities/{activity}"
    client.post(f"{base}/plan/confirm", json={"choices": [{"title": "Libreria", "type": "development"}]})
    client.post(f"{base}/plan/pause", json={"paused": False})

    closed = client.post(f"{base}/close", json={"learned": "- lib-auth prima dell'api\n\n* l'OTP in AuthFilter"}).json()

    assert closed["activity"] == activity and closed["context"] == "imparato.md"
    text = container.project_data_service.read_context("acme", "imparato.md")
    assert text.startswith(LEARNED_HEADER) and "## Login con OTP · " in text
    assert "- lib-auth prima dell'api\n- l'OTP in AuthFilter" in text
    assert container.project_data_service.activity("acme", activity).status.value == "done"
    assert stores.plans.latest("acme", activity).paused  # the round stops

    assert client.post(f"{base}/reopen").status_code == 204
    assert container.project_data_service.activity("acme", activity).status.value == "in_progress"
    assert container.project_data_service.read_context("acme", "imparato.md") == text  # the diary stays


def test_closing_with_nothing_learned_leaves_the_context_alone(client, container, activity):
    closed = client.post(f"/projects/acme/activities/{activity}/close", json={"learned": "  \n- "}).json()

    assert closed["context"] is None
    assert container.project_data_service.list_context("acme") == []
    assert container.project_data_service.activity("acme", activity).status.value == "done"


def test_the_newest_section_goes_first():
    first = with_section("", "## A · 01/11/2026\n- uno")
    second = with_section(first, "## B · 02/11/2026\n- due")

    assert second.index("## B") < second.index("## A") and second.startswith(LEARNED_HEADER)
    assert with_section("# Mio\n\nTesto mio.", "## C\n- tre") == "# Mio\n\nTesto mio.\n\n## C\n- tre\n"


def test_the_date_of_the_section(container, activity):
    service = container.activity_close_service
    service.close("acme", activity, "uno", today=date(2026, 11, 17))

    assert "## Login con OTP · 17/11/2026\n- uno" in container.project_data_service.read_context("acme", "imparato.md")
