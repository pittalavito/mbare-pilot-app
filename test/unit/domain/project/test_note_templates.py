"""The templates of the typed notes: markdown out, the same fields back, and
tolerant parsing of files edited by hand."""
from datetime import date

import pytest

from domain.project.data_paths import note_type, typed_note_file_name
from domain.project.note_templates import parse_agent_task, parse_todo_list, render_agent_task, render_todo_list
from models.domain.note import AgentTask, ChecklistItem, NoteType, TaskStatus, TodoItem, TodoList, TodoPriority

TASK = AgentTask(
    title="Refactor del login", status=TaskStatus.IN_PROGRESS, objective="Spostare l'auth nel service.\nSenza fretta.",
    context="Repository user-service.", criteria=[ChecklistItem(text="I test passano"), ChecklistItem(text="Nessuna API cambiata", done=True)],
    constraints="Non toccare lo schema del DB.",
)


def test_an_agent_task_is_readable_markdown_and_comes_back_the_same():
    text = render_agent_task(TASK)

    assert text.startswith("# Refactor del login\n\nStato: in corso\n\n## Obiettivo\nSpostare l'auth nel service.\nSenza fretta.\n")
    assert "## Criteri di accettazione\n- [ ] I test passano\n- [x] Nessuna API cambiata\n" in text
    assert parse_agent_task(text, "x") == TASK


def test_an_agent_task_edited_by_hand_keeps_what_the_template_knows():
    text = "Appunto libero\n\n## vincoli\nNiente fretta\n## Altro\nignorato\n## Criteri di accettazione\n* [X] fatto\nriga qualsiasi\n"

    task = parse_agent_task(text, "fix porto")

    assert task == AgentTask(title="fix porto", constraints="Niente fretta", criteria=[ChecklistItem(text="fatto", done=True)])


def test_a_todo_list_with_priorities_and_dates_comes_back_the_same():
    todo = TodoList(title="Rilascio v2", items=[
        TodoItem(text="Aggiornare le dipendenze", done=True, priority=TodoPriority.HIGH, due=date(2026, 10, 30)),
        TodoItem(text="Scrivere le note (bozza)", priority=TodoPriority.MEDIUM),
        TodoItem(text="Taggare il commit", due=date(2026, 11, 2)),
        TodoItem(text="Una voce\nsu due righe"),
    ])

    text = render_todo_list(todo)

    assert text == (
        "# Rilascio v2\n\n- [x] Aggiornare le dipendenze  (alta, 2026-10-30)\n- [ ] Scrivere le note (bozza)  (media)\n"
        "- [ ] Taggare il commit  (2026-11-02)\n- [ ] Una voce su due righe\n"
    )
    assert parse_todo_list(text, "x").items[:3] == todo.items[:3]


def test_parentheses_that_are_not_details_stay_in_the_text():
    todo = parse_todo_list("# Spesa\n- [ ] Pane (integrale)\n- [ ] Latte (2026-13-40)\n", "x")

    assert [(item.text, item.priority, item.due) for item in todo.items] == [("Pane (integrale)", None, None), ("Latte", None, None)]


@pytest.mark.parametrize("name, kind", [
    ("agent-task-refactor.md", NoteType.AGENT_TASK), ("Todo-List-rilascio.md", NoteType.TODO_LIST),
    ("decisioni.md", NoteType.GENERIC), ("agent-taskforce.md", NoteType.GENERIC),
])
def test_the_type_of_a_note_is_in_its_name(name, kind):
    assert note_type(name) == kind


def test_typed_notes_are_named_after_their_title():
    assert typed_note_file_name(NoteType.AGENT_TASK, "Refactor del Login!") == "agent-task-refactor-del-login.md"
    assert typed_note_file_name(NoteType.TODO_LIST, "???") == "todo-list-senza-titolo.md"


# ---------------------------------------------------------------- references

def test_references_round_trip_with_their_links():
    from domain.project.note_templates import parse_reference, render_reference
    from models.domain.note import Reference

    code = Reference(title="Login", source="jira", source_url="https://acme.atlassian.net/browse/NAV-7",
                     repository="api", path="src/auth/login.py", lines="10-40", content="Qui si controlla la password.")
    assert parse_reference(render_reference(code, code=True), "x") == code
    context = Reference(title="Procedura", source_url="https://wiki/x", repository="ignorato", content="Passi.")
    text = render_reference(context, code=False)
    assert "Repository" not in text and parse_reference(text, "x") == context.model_copy(update={"repository": ""})

    task = TASK.model_copy(update={"references": ["code-reference-login.md", "context-reference-procedura.md"]})
    assert parse_agent_task(render_agent_task(task), "x") == task
    todo = TodoList(title="Rilascio", items=[TodoItem(text="tag")], references=["context-reference-procedura.md"])
    assert parse_todo_list(render_todo_list(todo), "x") == todo
    assert "## Riferimenti" not in render_agent_task(TASK)  # only when there are some


def test_reference_names_and_hand_written_links():
    assert note_type("code-reference-login.md") is NoteType.CODE_REFERENCE
    assert note_type("context-reference-x.md") is NoteType.CONTEXT_REFERENCE and NoteType.CONTEXT_REFERENCE.is_reference
    assert typed_note_file_name(NoteType.CODE_REFERENCE, "Login OK") == "code-reference-login-ok.md"
    text = "# T\n\n- [ ] voce\n\n## Riferimenti\n* code-reference-a.md\n- [x] non un link\n- code-reference-a.md\n"
    todo = parse_todo_list(text, "x")
    assert todo.references == ["code-reference-a.md"] and [item.text for item in todo.items] == ["voce"]
