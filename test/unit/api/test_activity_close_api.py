"""Plan 18, the step «Chiudi»: the agent ``imparato`` proposes what to remember
(one structured call, fake model, a theme per point); closing writes each
point at the top of its theme in context/imparato.md (plan 27, indexed) and
makes the activity done; reopening keeps it."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.container import Container
from fakes import FakeStructuredClient as FakeClient
from models.domain.activity_close import LearnedAnswer, LearnedPoint
from models.domain.note import Activity, NoteType, Reference, TodoItem
from models.domain.project import Project, ProjectSource
from service.activity_close_service import LEARNED_HEADER, parse_points, with_point


@pytest.fixture
def model():
    return FakeClient(LearnedAnswer(points=[LearnedPoint(theme=" Build ", text=" lib-auth prima dell'api "), LearnedPoint(theme="", text="senza tema"),
                                            LearnedPoint(theme="X", text=" ")]))


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

    assert draft["points"] == [{"theme": "Build", "text": "lib-auth prima dell'api"}, {"theme": "Generale", "text": "senza tema"}]
    [call] = model.calls
    assert call["system_prompt"].startswith("Dall'attività finita") and "Attività: Login con OTP" in call["input"]
    assert "- Libreria (development, todo)" in call["input"]
    [run] = [run for run in stores.runs.list_runs() if run.run_id == draft["run_id"]]
    assert (run.origin, run.config_name) == ("learned", "imparato")


def test_a_failing_model_is_a_502(client, model, activity):
    model.error = RuntimeError("giù")

    assert client.post(f"/projects/acme/activities/{activity}/learned").status_code == 502


def test_closing_writes_each_point_under_its_theme_and_reopening_keeps_it(client, container, activity, stores):
    base = f"/projects/acme/activities/{activity}"
    client.post(f"{base}/plan/confirm", json={"choices": [{"title": "Libreria", "type": "development"}]})
    client.post(f"{base}/plan/pause", json={"paused": False})

    closed = client.post(f"{base}/close", json={"learned": "- Build: lib-auth prima dell'api\n\n* l'OTP in AuthFilter"}).json()

    assert closed["activity"] == activity and closed["context"] == "imparato.md"
    text = container.project_data_service.read_context("acme", "imparato.md")
    assert text.startswith(LEARNED_HEADER) and "## Build\n- lib-auth prima dell'api (Login con OTP, " in text
    assert "## Generale\n- l'OTP in AuthFilter (Login con OTP, " in text
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


def test_points_go_at_the_top_of_their_theme():
    first = with_point("", "Build", "uno")
    second = with_point(with_point(first, "build", "due"), "Test", "tre")

    assert second.startswith(LEARNED_HEADER) and "## Build\n- due\n- uno" in second and second.endswith("## Test\n- tre\n")
    assert with_point("# Mio\n\nTesto mio.", "C", "x") == "# Mio\n\nTesto mio.\n\n## C\n- x\n"
    assert parse_points("- Build: a\nnessun tema\n" + "x" * 50 + ": lungo\nTema:\n") == [
        LearnedPoint(theme="Build", text="a"), LearnedPoint(theme="Generale", text="nessun tema"),
        LearnedPoint(theme="Generale", text="x" * 50 + ": lungo"), LearnedPoint(theme="Generale", text="Tema:")]


def test_the_date_of_the_section(container, activity):
    service = container.activity_close_service
    service.close("acme", activity, "uno", today=date(2026, 11, 17))

    assert "## Generale\n- uno (Login con OTP, 17/11/2026)" in container.project_data_service.read_context("acme", "imparato.md")


def test_archiving_leaves_a_summary_and_deletes_what_was_chosen(client, container, activity):
    """Plan 33: «🗄 Archivia» a closed activity."""
    data = container.project_data_service
    base = f"/projects/acme/activities/{activity}"
    keep = data.create_reference("acme", NoteType.CONTEXT_REFERENCE, Reference(title="Resta", content="x"))
    gone = data.create_reference("acme", NoteType.CONTEXT_REFERENCE, Reference(title="Pagina", content="y", source="confluence",
                                                                            source_url="https://acme.atlassian.net/wiki/x"))
    data.save_activity("acme", activity, data.activity("acme", activity).model_copy(update={"references": [keep, gone]}))
    client.post(f"{base}/plan/confirm", json={"choices": [{"title": "Analizza", "type": "analysis"}]})
    task = container.plan_service.plan("acme", activity).tasks[0].task
    data.save_note("acme", "analisi-analizza.md", "# Analisi\\n")
    data.save_agent_task("acme", task, data.agent_task("acme", task).model_copy(update={"status": "done"}))
    assert client.post(f"{base}/archive", json={}).status_code == 409  # not closed yet
    client.post(f"{base}/close", json={"learned": ""})

    archived = client.post(f"{base}/archive", json={"delete_references": [gone]}).json()

    assert archived["note"] == "archivio-login-con-otp.md"
    summary = data.read_note("acme", archived["note"])
    assert summary.startswith("# Archivio: Login con OTP") and "- [ ] a" in summary and "✓ Analizza (analysis)" in summary
    assert "[Pagina](https://acme.atlassian.net/wiki/x)" in summary
    assert set(archived["deleted"]) == {task, "analisi-analizza.md", gone, activity}
    assert data.note_exists("acme", keep.removesuffix(".md")) or keep in [name for name, _, _ in data.references("acme")]
    assert container.plan_service.plan("acme", activity).tasks == []
