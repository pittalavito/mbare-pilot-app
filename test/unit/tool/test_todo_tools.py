"""The secretary's tools: todo lists (list, read, create, add and tick items,
never the references) and the agent tasks' status without Copilot. Only in a
chatbot's run of a project."""
from datetime import date

import pytest

from fakes import as_dict
from models.domain.agent import RunOrigin
from models.domain.note import AgentTask, TaskStatus, TodoItem, TodoList
from models.domain.project import Project, ProjectSource
from service.project_data_service import ProjectDataService
from tool.context import ToolContext
from tool.list.copilot.list_agent_tasks import LIST_AGENT_TASKS
from tool.list.notes.todo_lists import CREATE_TODO_LIST, LIST_TODO_LISTS, READ_TODO_LIST, UPDATE_TODO_LIST

REFERENCE = "context-reference-procedura.md"


@pytest.fixture
def context(store_service) -> ToolContext:
    """Chatbot run of ``acme`` (no Copilot) with the list «Rilascio», linked to a reference."""
    store_service.save_project(Project(name="acme", source=ProjectSource.FOLDER, root_path="/code/acme"))
    data = ProjectDataService(store_service)
    store_service.save_file(f"acme/notes/{REFERENCE}", b"# Procedura\n\n## Contenuto\nsegreto\n")
    data.create_todo_list("acme", TodoList(title="Rilascio", references=[REFERENCE], items=[
        TodoItem(text="Aggiornare le dipendenze", done=True), TodoItem(text="Taggare il commit"),
    ]))
    return ToolContext(project_name="acme", git=None, origin=RunOrigin.CHAT, project_data=data)


def _call(spec, context, **kwargs):
    return as_dict(spec.build(context).func(**kwargs))


def test_lists_and_reads_the_todo_lists_without_their_references(context):
    today = date.today().isoformat()

    assert _call(LIST_TODO_LISTS, context) == {
        "today": today, "todo_lists": [{"name": "todo-list-rilascio.md", "title": "Rilascio", "done": 1, "total": 2}],
    }
    read = _call(READ_TODO_LIST, context, name="todo-list-rilascio.md")
    assert [(item["number"], item["text"], item["done"]) for item in read["items"]] == [
        (1, "Aggiornare le dipendenze", True), (2, "Taggare il commit", False),
    ]
    assert "reference" not in str(read) and "segreto" not in str(read)


def test_creates_a_list_with_priority_and_due_date(context):
    created = _call(CREATE_TODO_LIST, context, title="Spesa ufficio", items=["Caffè  (alta, 2026-11-02)", "Carta", " "])

    assert created["name"] == "todo-list-spesa-ufficio.md"
    assert [(item["text"], item["priority"], item["due"]) for item in created["items"]] == [
        ("Caffè", "high", "2026-11-02"), ("Carta", None, None),
    ]
    saved = context.project_data.todo_list("acme", "todo-list-spesa-ufficio.md")
    assert saved.items[0].priority.value == "high" and len(saved.items) == 2


def test_adds_and_ticks_items_and_keeps_the_references(context):
    updated = _call(UPDATE_TODO_LIST, context, name="todo-list-rilascio.md", add=["Scrivere le note"], check=[2], uncheck=[1])

    assert [(item["text"], item["done"]) for item in updated["items"]] == [
        ("Aggiornare le dipendenze", False), ("Taggare il commit", True), ("Scrivere le note", False),
    ]
    assert context.project_data.todo_list("acme", "todo-list-rilascio.md").references == [REFERENCE]


def test_errors_come_back_to_the_chatbot(context):
    wrong = _call(UPDATE_TODO_LIST, context, name="todo-list-rilascio.md", add=[], check=[3], uncheck=[])
    assert "Voci inesistenti: 3" in wrong["error"]
    assert "non è una todo list" in _call(READ_TODO_LIST, context, name=REFERENCE)["error"]
    assert "not found" in _call(READ_TODO_LIST, context, name="todo-list-altro.md")["error"]
    assert "titolo" in _call(CREATE_TODO_LIST, context, title=" ", items=[])["error"]


def test_the_agent_tasks_status_also_without_copilot(context):
    context.project_data.create_agent_task("acme", AgentTask(title="Fix porto", status=TaskStatus.IN_PROGRESS))

    assert _call(LIST_AGENT_TASKS, context) == {"tasks": [
        {"task": "agent-task-fix-porto.md", "title": "Fix porto", "status": "in_progress", "copilot_status": None},
    ]}


def test_only_in_a_chatbot_run(context):
    manual = ToolContext(project_name="acme", git=None, origin=RunOrigin.MANUAL, project_data=context.project_data)

    for spec, kwargs in ((LIST_TODO_LISTS, {}), (READ_TODO_LIST, {"name": "todo-list-rilascio.md"}),
                         (CREATE_TODO_LIST, {"title": "X", "items": []}),
                         (UPDATE_TODO_LIST, {"name": "todo-list-rilascio.md", "add": [], "check": [], "uncheck": []})):
        assert "solo nel chatbot" in _call(spec, manual, **kwargs)["error"]
