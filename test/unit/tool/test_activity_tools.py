"""The secretary's tools: activities (list, read, create, change description
and status, add and tick items; never the references) and the agent tasks'
status without Copilot. Only in a chatbot's run of a project."""
from datetime import date

import pytest

from fakes import as_dict
from models.domain.agent import RunOrigin
from models.domain.note import Activity, ActivityStatus, AgentTask, TaskStatus, TodoItem
from models.domain.project import Project, ProjectSource
from tool.context import ToolContext
from tool.list.copilot.list_agent_tasks import LIST_AGENT_TASKS
from tool.list.notes.activities import CREATE_ACTIVITY, LIST_ACTIVITIES, READ_ACTIVITY, UPDATE_ACTIVITY

REFERENCE = "context-reference-procedura.md"
RILASCIO = "attivita-rilascio.md"


@pytest.fixture
def context(project_data_service, project_store, project_file_store) -> ToolContext:
    """Chatbot run of ``acme`` (no Copilot) with the activity «Rilascio», linked to a reference and to two agent tasks (one deleted)."""
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path="/code/acme"))
    data = project_data_service
    project_file_store.save(f"acme/notes/{REFERENCE}", b"# Procedura\n\n## Contenuto\nsegreto\n")
    task = data.create_agent_task("acme", AgentTask(title="Note di rilascio", status=TaskStatus.REFINEMENT))
    data.create_activity("acme", Activity(
        title="Rilascio", description="La 2.0", references=[REFERENCE], agent_tasks=[task, "agent-task-sparito.md"],
        items=[TodoItem(text="Aggiornare le dipendenze", done=True), TodoItem(text="Taggare il commit")],
    ))
    return ToolContext(project_name="acme", git=None, origin=RunOrigin.CHAT, project_data=data)


def _call(spec, run, **kwargs):
    return as_dict(spec.build(run).func(**kwargs))


def _update(run, **fields):
    return _call(UPDATE_ACTIVITY, run, **{"name": RILASCIO, "description": "", "status": "", "add": [], "check": [], "uncheck": [], **fields})


def test_lists_and_reads_the_activities_without_their_references(context):
    today = date.today().isoformat()

    assert _call(LIST_ACTIVITIES, context) == {"today": today, "activities": [
        {"name": RILASCIO, "title": "Rilascio", "status": "todo", "done": 1, "total": 2, "agent_tasks": 2},
    ]}
    read = _call(READ_ACTIVITY, context, name="attivita-rilascio")
    assert (read["title"], read["status"], read["description"], read["today"]) == ("Rilascio", "todo", "La 2.0", today)
    assert [(item["number"], item["text"], item["done"]) for item in read["items"]] == [
        (1, "Aggiornare le dipendenze", True), (2, "Taggare il commit", False),
    ]
    assert read["agent_tasks"] == [{"task": "agent-task-note-di-rilascio.md", "title": "Note di rilascio", "status": "refinement"}]  # the deleted one left out
    assert "reference" not in str(read) and "segreto" not in str(read)


def test_creates_an_activity_with_description_and_its_todo_list(context):
    created = _call(CREATE_ACTIVITY, context, title="Spesa ufficio", description=" Per la riunione ", items=["Caffè  (alta, 2026-11-02)", "Carta", " "])

    assert (created["name"], created["status"], created["description"]) == ("attivita-spesa-ufficio.md", "todo", "Per la riunione")
    assert [(item["text"], item["priority"], item["due"]) for item in created["items"]] == [("Caffè", "high", "2026-11-02"), ("Carta", None, None)]
    saved = context.project_data.activity("acme", "attivita-spesa-ufficio.md")
    assert saved.items[0].priority.value == "high" and len(saved.items) == 2


def test_changes_description_status_and_items_and_keeps_the_links(context):
    updated = _update(context, description="La 2.0, entro venerdì", status="in_progress", add=["Scrivere le note"], check=[2], uncheck=[1])

    assert (updated["description"], updated["status"]) == ("La 2.0, entro venerdì", "in_progress")
    assert [(item["text"], item["done"]) for item in updated["items"]] == [
        ("Aggiornare le dipendenze", False), ("Taggare il commit", True), ("Scrivere le note", False),
    ]
    activity = context.project_data.activity("acme", RILASCIO)
    assert activity.references == [REFERENCE] and activity.agent_tasks == ["agent-task-note-di-rilascio.md", "agent-task-sparito.md"]

    unchanged = _update(context)
    assert (unchanged["description"], unchanged["status"]) == ("La 2.0, entro venerdì", "in_progress")
    assert _update(context, status="done")["status"] == "done" and context.project_data.activity("acme", RILASCIO).status == ActivityStatus.DONE


def test_errors_come_back_to_the_chatbot(context):
    assert "Voci inesistenti: 3" in _update(context, check=[3])["error"]
    assert "Stato non valido" in _update(context, status="finita")["error"]
    assert "non è un'attività" in _call(READ_ACTIVITY, context, name=REFERENCE)["error"]
    assert "not found" in _call(READ_ACTIVITY, context, name="attivita-altra.md")["error"]
    assert "titolo" in _call(CREATE_ACTIVITY, context, title=" ", description="", items=[])["error"]
    assert "Esiste già" in _call(CREATE_ACTIVITY, context, title="Rilascio", description="", items=[])["error"]
    assert "error" in _update(context, name="attivita-altra.md")


def test_the_agent_tasks_status_also_without_copilot(context):
    context.project_data.create_agent_task("acme", AgentTask(title="Fix porto", status=TaskStatus.IN_PROGRESS))

    assert _call(LIST_AGENT_TASKS, context)["tasks"][0] == {
        "task": "agent-task-fix-porto.md", "title": "Fix porto", "status": "in_progress", "type": "development", "copilot_status": None,
    }


def test_only_in_a_chatbot_run(context):
    manual = ToolContext(project_name="acme", git=None, origin=RunOrigin.MANUAL, project_data=context.project_data)

    for spec, kwargs in ((LIST_ACTIVITIES, {}), (READ_ACTIVITY, {"name": RILASCIO}),
                         (CREATE_ACTIVITY, {"title": "X", "description": "", "items": []})):
        assert "solo nel chatbot" in _call(spec, manual, **kwargs)["error"]
    assert "solo nel chatbot" in _update(manual)["error"]
    other = ToolContext(project_name="manca", git=None, origin=RunOrigin.CHAT, project_data=context.project_data)
    assert "error" in _call(LIST_ACTIVITIES, other)
