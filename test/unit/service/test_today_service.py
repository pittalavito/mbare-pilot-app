"""«📌 Oggi»: who waits, overdue and due soon items, activities to close, the
two quick actions on an item, the secretary's tool and the API."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.container import Container
from core.error import ConflictError, ValidationError
from fakes import as_dict
from models.domain.agent import RunOrigin
from models.domain.copilot import CopilotMessage, CopilotMessageRole, CopilotSession, CopilotSessionStatus
from models.domain.note import Activity, ActivityStatus, AgentTask, TaskStatus, TodoItem
from models.domain.project import Project, ProjectSource
from service.copilot_service import CopilotService
from service.today_service import TodayService
from tool.context import ToolContext
from tool.list.notes.today import TODAY

TODAY_DATE = date(2026, 11, 10)


@pytest.fixture
def setup(project_store, project_data_service, copilot_store, definition_store, git_service):
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path="/code/acme"))
    data = project_data_service
    copilot = CopilotService.from_config(definition_store, copilot_store, git_service, data)
    return data, copilot, copilot_store, TodayService(data, copilot)


def _session(store, task: str, status: CopilotSessionStatus, *roles: CopilotMessageRole) -> CopilotSession:
    session = store.save_session(CopilotSession(project_name="acme", task_note=task, copilot_session_id=f"s-{task}-{status}-{len(roles)}", status=status))
    for role in roles:
        store.add_message(CopilotMessage(session_id=session.id, role=role, content="…"))
    return session


def test_the_sections(setup):
    data, _, store, service = setup
    for title, status in (("Nuovo", TaskStatus.CREATED), ("Da rifinire", TaskStatus.REFINEMENT), ("Pronto", TaskStatus.TODO),
                          ("Verifica", TaskStatus.TO_VERIFY), ("Chiuso", TaskStatus.DONE)):
        data.create_agent_task("acme", AgentTask(title=title, status=status))
    asks = _session(store, "agent-task-pronto.md", CopilotSessionStatus.PLANNING, CopilotMessageRole.USER, CopilotMessageRole.COPILOT,
                    CopilotMessageRole.EVENT)
    _session(store, "agent-task-pronto.md", CopilotSessionStatus.PLANNING, CopilotMessageRole.COPILOT, CopilotMessageRole.USER)  # my turn done
    question = _session(store, "agent-task-verifica.md", CopilotSessionStatus.RUNNING, CopilotMessageRole.QUESTION)
    _session(store, "agent-task-chiuso.md", CopilotSessionStatus.RUNNING, CopilotMessageRole.QUESTION, CopilotMessageRole.USER)  # answered
    _session(store, "agent-task-chiuso.md", CopilotSessionStatus.DONE, CopilotMessageRole.COPILOT)
    _session(store, "agent-task-cancellato.md", CopilotSessionStatus.PLANNING, CopilotMessageRole.COPILOT)  # its task is gone
    data.create_activity("acme", Activity(title="Rilascio", items=[
        TodoItem(text="Vecchia", due=date(2026, 11, 1)), TodoItem(text="Ieri", due=date(2026, 11, 9)), TodoItem(text="Oggi", due=TODAY_DATE),
        TodoItem(text="Tra tre giorni", due=date(2026, 11, 13)), TodoItem(text="Tra quattro", due=date(2026, 11, 14)),
        TodoItem(text="Fatta scaduta", due=date(2026, 11, 1), done=True), TodoItem(text="Senza data"),
    ]))
    data.create_activity("acme", Activity(title="Finita", items=[TodoItem(text="a", done=True), TodoItem(text="b", done=True)]))
    data.create_activity("acme", Activity(title="Chiusa", status=ActivityStatus.DONE, items=[TodoItem(text="x", due=date(2026, 11, 1))]))
    data.create_activity("acme", Activity(title="Vuota"))

    today = service.today("acme", TODAY_DATE)

    assert [(item.kind.value, item.title, item.status, item.session_id) for item in today.waiting] == [
        ("task", "Nuovo", "created", None), ("task", "Da rifinire", "refinement", None), ("task", "Verifica", "to_verify", None),
        ("copilot", "Verifica", "question", question.id), ("copilot", "Pronto", "answer", asks.id),  # newest session first
    ]
    assert [(item.text, item.item) for item in today.overdue] == [("Vecchia", 1), ("Ieri", 2)]
    assert [item.text for item in today.due_soon] == ["Oggi", "Tra tre giorni"]
    assert [(item.title, item.items) for item in today.to_close] == [("Finita", 2)]
    assert today.due_soon_days == 3

    data.save_due_soon_days("acme", 4)
    assert [item.text for item in service.today("acme", TODAY_DATE).due_soon] == ["Oggi", "Tra tre giorni", "Tra quattro"]


def test_check_and_postpone_an_item_unless_it_changed(setup):
    data, _, _, service = setup
    name = data.create_activity("acme", Activity(title="Rilascio", items=[TodoItem(text="Note", due=date(2026, 11, 1)), TodoItem(text="Tag")]))

    service.set_due("acme", name, 1, "Note", date(2026, 11, 17))
    service.check_item("acme", "attivita-rilascio", 2, "Tag")

    items = data.activity("acme", name).items
    assert [(item.text, item.done, item.due) for item in items] == [("Note", False, date(2026, 11, 17)), ("Tag", True, None)]
    with pytest.raises(ConflictError, match="già fatta"):
        service.check_item("acme", name, 2, "Tag")
    with pytest.raises(ConflictError, match="cambiata"):
        service.check_item("acme", name, 1, "Note di rilascio")
    with pytest.raises(ValidationError, match="Voce 3"):
        service.set_due("acme", name, 3, "x", date(2026, 11, 20))


def test_the_secretary_s_tool_is_compact(setup):
    data, copilot, _, _ = setup
    data.create_agent_task("acme", AgentTask(title="Nuovo"))
    data.create_activity("acme", Activity(title="Rilascio", items=[TodoItem(text="Note", due=date(2000, 1, 1))]))
    run = ToolContext(project_name="acme", git=None, origin=RunOrigin.CHAT, project_data=data, copilot=copilot)  # type: ignore[arg-type]

    answer = as_dict(TODAY.build(run).func())

    assert answer["waiting"] == ["Nuovo (agent-task-nuovo.md): created"]
    assert answer["overdue"] == ["Rilascio · voce 1 «Note» · scaduta il 2000-01-01"]
    assert answer["due_soon"] == [] and answer["to_close"] == [] and answer["due_soon_days"] == 3
    outside = ToolContext(project_name="acme", git=None, origin=RunOrigin.MANUAL, project_data=data, copilot=copilot)  # type: ignore[arg-type]
    assert "solo nel chatbot" in as_dict(TODAY.build(outside).func())["error"]
    broken = ToolContext(project_name="manca", git=None, origin=RunOrigin.CHAT, project_data=data, copilot=copilot)  # type: ignore[arg-type]
    assert "manca" in as_dict(TODAY.build(broken).func())["error"]
    no_copilot = ToolContext(project_name="acme", git=None, origin=RunOrigin.CHAT, project_data=data)  # type: ignore[arg-type]
    assert as_dict(TODAY.build(no_copilot).func())["waiting"] == ["Nuovo (agent-task-nuovo.md): created"]


def test_the_api(stores, project_store, tmp_path):
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path=str(tmp_path)))
    with TestClient(create_app(Container(stores=stores))) as client:
        name = client.post("/projects/acme/activities", json={"title": "Rilascio", "items": [{"text": "Note", "due": "2000-01-01"}]}).json()["name"]

        assert [item["text"] for item in client.get("/projects/acme/today").json()["overdue"]] == ["Note"]
        assert client.post(f"/projects/acme/activities/{name}/items/1/due", json={"text": "Note", "due": "2999-01-01"}).status_code == 204
        assert client.get("/projects/acme/today").json()["overdue"] == []
        assert client.post(f"/projects/acme/activities/{name}/items/1/check", json={"text": "Altro"}).status_code == 409
        assert client.post(f"/projects/acme/activities/{name}/items/1/check", json={"text": "Note"}).status_code == 204
        assert [item["title"] for item in client.get("/projects/acme/today").json()["to_close"]] == ["Rilascio"]
