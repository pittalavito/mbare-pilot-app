"""Blocco 08: an item remembers the agent task born from it (``→ agent-task-….md``
on its line) and is checked by itself when the task gets «done»."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.container import Container
from core.error import ConflictError, ValidationError
from domain.project.note_templates import parse_activity, render_activity
from models.domain.copilot import CopilotSession, CopilotSessionStatus
from models.domain.note import Activity, AgentTask, TaskStatus, TaskType, TodoItem, TodoPriority
from models.domain.project import Project, ProjectSource
from service.copilot_service import CopilotService

TASK = "agent-task-note-di-rilascio.md"


@pytest.fixture
def data(project_store, project_data_service):
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path="/code/acme"))
    return project_data_service


def _release(data, task_status: TaskStatus = TaskStatus.TODO) -> str:
    data.create_agent_task("acme", AgentTask(title="Note di rilascio", status=task_status))
    return data.create_activity("acme", Activity(title="Rilascio", description="La 2.0", references=["note-varie.md"], items=[
        TodoItem(text="Dipendenze", done=True),
        TodoItem(text="Note di rilascio", priority=TodoPriority.MEDIUM, due=date(2026, 11, 20), agent_task=TASK),
    ]))


def test_the_arrow_on_the_line_keeps_priority_and_due():
    activity = Activity(title="Rilascio", items=[
        TodoItem(text="Note", priority=TodoPriority.MEDIUM, due=date(2026, 11, 20), agent_task=TASK),
        TodoItem(text="Solo task", agent_task="agent-task-solo.md"), TodoItem(text="Freccia → qualcosa"),
    ])

    text = render_activity(activity)

    assert f"- [ ] Note  (media, 2026-11-20)  → {TASK}" in text
    assert "- [ ] Solo task  → agent-task-solo.md" in text
    assert parse_activity(text, "x").items == activity.items  # an arrow to something else is part of the text
    assert parse_activity("## Todo\n- [x] Fatto (alta)  → agent-task-a.md\n", "x").items == [
        TodoItem(text="Fatto", done=True, priority=TodoPriority.HIGH, agent_task="agent-task-a.md")]


def test_the_item_follows_its_task_done_and_back(data):
    activity = _release(data)
    task = data.agent_task("acme", TASK)

    assert data.save_agent_task("acme", TASK, task.model_copy(update={"status": TaskStatus.TO_VERIFY})) == []  # not yet
    assert not data.activity("acme", activity).items[1].done

    changes = data.save_agent_task("acme", TASK, task.model_copy(update={"status": TaskStatus.DONE}))
    assert [(change.activity, change.activity_title, change.item, change.text, change.done) for change in changes] == [
        (activity, "Rilascio", 2, "Note di rilascio", True)]
    assert data.activity("acme", activity).items[1].done
    assert data.save_agent_task("acme", TASK, task.model_copy(update={"status": TaskStatus.DONE, "objective": "x"})) == []  # still done

    changes = data.save_agent_task("acme", TASK, task.model_copy(update={"status": TaskStatus.TODO}))
    assert [change.done for change in changes] == [False]
    items = data.activity("acme", activity).items
    assert [(item.done, item.priority, item.due, item.agent_task) for item in items] == [
        (True, None, None, None), (False, TodoPriority.MEDIUM, date(2026, 11, 20), TASK)]
    assert data.activity("acme", activity).status.value == "todo"  # the activity never changes by itself


def test_copilot_s_status_changes_check_the_item(data, copilot_store, definition_store, git_service):
    activity = _release(data, TaskStatus.IN_PROGRESS)
    copilot = CopilotService.from_config(definition_store, copilot_store, git_service, data)
    session = copilot_store.save_session(CopilotSession(project_name="acme", task_note=TASK, copilot_session_id="s", status=CopilotSessionStatus.DONE))

    copilot._set_task_status(session, TaskStatus.DONE)

    assert data.activity("acme", activity).items[1].done


def test_an_item_s_task_is_among_the_activity_s_and_deleting_it_unlinks_the_item(data):
    activity = _release(data)
    assert data.activity("acme", activity).agent_tasks == [TASK]

    data.delete_note("acme", TASK)

    items = data.activity("acme", activity).items
    assert [item.agent_task for item in items] == [None, None] and items[1].text == "Note di rilascio"
    assert data.activity("acme", activity).agent_tasks == []


def test_a_task_from_an_item(data):
    activity = _release(data)
    data.save_activity("acme", activity, data.activity("acme", activity).model_copy(
        update={"items": [*data.activity("acme", activity).items, TodoItem(text="Taggare")]}))

    name = data.create_task_from_item("acme", activity, 3, "Taggare", TaskType.ANALYSIS)

    task = data.agent_task("acme", name)
    assert (name, task.title, task.status, task.type, task.references) == (
        "agent-task-taggare.md", "Taggare", TaskStatus.CREATED, TaskType.ANALYSIS, ["note-varie.md"])
    assert task.context == "Nasce dalla voce 3 dell'attività «Rilascio».\n\nLa 2.0"
    saved = data.activity("acme", activity)
    assert saved.items[2].agent_task == name and saved.agent_tasks == [TASK, name]
    with pytest.raises(ConflictError, match="già un agent task"):
        data.create_task_from_item("acme", activity, 3, "Taggare", TaskType.DEVELOPMENT)
    with pytest.raises(ConflictError, match="cambiata"):
        data.create_task_from_item("acme", activity, 1, "Altro", TaskType.DEVELOPMENT)
    with pytest.raises(ValidationError, match="Voce 9"):
        data.link_item("acme", activity, 9, name)


def test_the_api(stores, project_store, tmp_path):
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path=str(tmp_path)))
    with TestClient(create_app(Container(stores=stores))) as client:
        name = client.post("/projects/acme/activities", json={"title": "Rilascio", "items": [{"text": "Note"}]}).json()["name"]

        created = client.post(f"/projects/acme/activities/{name}/items/1/agent-task", json={"text": "Note", "type": "analysis"})
        assert created.status_code == 201
        task = created.json()
        assert (task["name"], task["status"], task["type"]) == ("agent-task-note.md", "created", "analysis")
        assert client.get("/projects/acme/activities").json()[0]["items"][0]["agent_task"] == "agent-task-note.md"
        assert client.post(f"/projects/acme/activities/{name}/items/1/agent-task", json={"text": "Note"}).status_code == 409

        body = {key: value for key, value in task.items() if key != "name"} | {"status": "done"}
        saved = client.put("/projects/acme/agent-tasks/agent-task-note.md", json=body).json()
        assert saved["items_changed"] == [{"activity": name, "activity_title": "Rilascio", "item": 1, "text": "Note", "done": True}]
        assert client.get("/projects/acme/activities").json()[0]["items"][0]["done"] is True
