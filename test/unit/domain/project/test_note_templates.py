"""The templates of the typed notes: markdown out, the same fields back, and
tolerant parsing of files edited by hand."""
from datetime import date

import pytest

from domain.project.data_paths import note_type, typed_note_file_name
from domain.project.note_templates import parse_activity, parse_agent_task, render_activity, render_agent_task
from models.domain.note import Activity, ActivityStatus, AgentTask, ChecklistItem, NoteType, TaskStatus, TaskType, TodoItem, TodoPriority

TASK = AgentTask(
    title="Refactor del login", status=TaskStatus.IN_PROGRESS, objective="Spostare l'auth nel service.\nSenza fretta.",
    context="Repository user-service.", criteria=[ChecklistItem(text="I test passano"), ChecklistItem(text="Nessuna API cambiata", done=True)],
    constraints="Non toccare lo schema del DB.",
)


def test_an_agent_task_is_readable_markdown_and_comes_back_the_same():
    text = render_agent_task(TASK)

    assert text.startswith("# Refactor del login\n\nStato: in corso\nTipo: sviluppo\n\n## Obiettivo\nSpostare l'auth nel service.\nSenza fretta.\n")
    assert "## Criteri di accettazione\n- [ ] I test passano\n- [x] Nessuna API cambiata\n" in text
    assert parse_agent_task(text, "x") == TASK


def test_an_agent_task_edited_by_hand_keeps_what_the_template_knows():
    text = "Appunto libero\n\n## vincoli\nNiente fretta\n## Altro\nresta\n## Criteri di accettazione\n* [X] fatto\nriga qualsiasi\n"

    task = parse_agent_task(text, "fix porto")

    # an unknown heading is text of the section above it: nothing is lost on the next save
    assert task == AgentTask(title="fix porto", constraints="Niente fretta\n## Altro\nresta", criteria=[ChecklistItem(text="fatto", done=True)])


@pytest.mark.parametrize("status", list(TaskStatus))
@pytest.mark.parametrize("kind", list(TaskType))
def test_every_status_and_type_comes_back_the_same(status, kind):
    task = AgentTask(title="Giro", status=status, type=kind)

    assert parse_agent_task(render_agent_task(task), "x") == task


def test_status_and_type_written_by_hand():
    task = parse_agent_task("# Analisi\n\nStato: In Rifinitura\nTipo: ANALISI\n", "x")
    assert (task.status, task.type) == (TaskStatus.REFINEMENT, TaskType.ANALYSIS)

    # missing or unknown: a task not refined yet, to develop
    assert parse_agent_task("# Senza\n", "x").status == TaskStatus.CREATED
    task = parse_agent_task("# Strano\n\nStato: boh\nTipo: boh\n", "x")
    assert (task.status, task.type) == (TaskStatus.CREATED, TaskType.DEVELOPMENT)
    assert [status.is_refined for status in TaskStatus] == [False, False, True, True, True, True]


def test_the_new_types_and_status_are_written_in_italian_and_the_old_refinement_type_reads_as_jira():
    text = render_agent_task(AgentTask(title="Doc", status=TaskStatus.TO_VERIFY, type=TaskType.CONFLUENCE))
    assert "Stato: da verificare\nTipo: doc confluence\n" in text
    assert parse_agent_task("# Storia\n\nTipo: Task Jira\n", "x").type == TaskType.JIRA

    old = parse_agent_task("# Storia\n\nStato: da fare\nTipo: rifinitura\n", "x")  # «rifinire una storia», before jira
    assert (old.status, old.type) == (TaskStatus.TODO, TaskType.JIRA)
    assert "Tipo: task jira" in render_agent_task(old)  # rewritten only when saved


def test_imparato_is_written_only_when_there_is_something_and_comes_back():
    activity = Activity(title="Rilascio", status=ActivityStatus.DONE, learned="Le note prima del tag.\nE il changelog.")

    text = render_activity(activity)

    assert "## Imparato\nLe note prima del tag.\nE il changelog.\n" in text
    assert parse_activity(text, "x") == activity
    assert "## Imparato" not in render_activity(Activity(title="Vuota"))


def test_only_a_development_is_executed_by_copilot():
    assert [kind for kind in TaskType if not kind.plan_only] == [TaskType.DEVELOPMENT]


def test_markdown_headings_inside_a_section_do_not_cut_it():
    context = "Dalla issue NAV-7.\n\n## Passi\n\n1. apri\n\n## Atteso\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n\n# Titolo grande\nfine"
    task = AgentTask(title="Da Jira", context=context, constraints="Nessuno", references=["context-reference-nav-7.md"])

    assert parse_agent_task(render_agent_task(task), "x") == task


def test_reference_content_with_its_own_headings_comes_back_whole():
    from domain.project.note_templates import parse_reference, render_reference
    from models.domain.note import Reference

    content = "Tipo: Bug\n\n## Passi\n\n1. apri\n\n## Riferimenti\n- non è una sezione qui\n\n```bash\n## commento\n```"
    reference = Reference(title="NAV-7 · Login", source="jira", source_url="https://acme.atlassian.net/browse/NAV-7", content=content)

    assert parse_reference(render_reference(reference, code=False), "x") == reference


def test_an_activity_is_readable_markdown_and_comes_back_the_same():
    activity = Activity(
        title="Rilascio v2", status=ActivityStatus.IN_PROGRESS, description="Preparare la 2.0.\n\n## Note\nentro fine mese",
        items=[
            TodoItem(text="Aggiornare le dipendenze", done=True, priority=TodoPriority.HIGH, due=date(2026, 10, 30)),
            TodoItem(text="Scrivere le note (bozza)", priority=TodoPriority.MEDIUM),
            TodoItem(text="Taggare il commit", due=date(2026, 11, 2)),
        ],
        agent_tasks=["agent-task-note-di-rilascio.md"], references=["context-reference-procedura.md"],
    )

    text = render_activity(activity)

    assert text == (
        "# Rilascio v2\n\nStato: in corso\n\n## Descrizione\nPreparare la 2.0.\n\n## Note\nentro fine mese\n\n"
        "## Todo\n- [x] Aggiornare le dipendenze  (alta, 2026-10-30)\n- [ ] Scrivere le note (bozza)  (media)\n"
        "- [ ] Taggare il commit  (2026-11-02)\n\n## Agent task\n- agent-task-note-di-rilascio.md\n\n"
        "## Riferimenti\n- context-reference-procedura.md\n"
    )
    assert parse_activity(text, "x") == activity
    empty = render_activity(Activity(title="Vuota"))
    assert empty == "# Vuota\n\nStato: da fare\n\n## Descrizione\n\n## Todo\n" and parse_activity(empty, "x") == Activity(title="Vuota")


@pytest.mark.parametrize("items, status", [
    ("- [x] uno\n- [x] due\n", ActivityStatus.DONE),
    ("- [x] uno\n- [ ] due\n", ActivityStatus.TODO),
    ("", ActivityStatus.TODO),
])
def test_an_old_todo_list_reads_as_an_activity(items, status):
    activity = parse_activity(f"# Rilascio\n\n{items}## Riferimenti\n- context-reference-procedura.md\n", "x")

    assert (activity.title, activity.status, activity.description, activity.agent_tasks) == ("Rilascio", status, "", [])
    assert [item.text for item in activity.items] == [line[6:] for line in items.splitlines()]
    assert activity.references == ["context-reference-procedura.md"]


def test_an_activity_status_written_by_hand():
    assert parse_activity("# A\n\nStato: FATTA\n", "x").status == ActivityStatus.DONE
    assert parse_activity("# A\n\nStato: boh\n\n## Todo\n- [x] uno\n", "x").status == ActivityStatus.DONE  # from the items
    assert parse_activity("# A\n\nStato: in corso\n\n## Todo\n- [x] uno\n", "x").status == ActivityStatus.IN_PROGRESS  # as written


def test_a_todo_item_written_on_two_lines_becomes_one():
    text = render_activity(Activity(title="A", items=[TodoItem(text="Una voce\nsu due righe")]))
    assert "- [ ] Una voce su due righe\n" in text


def test_parentheses_that_are_not_details_stay_in_the_text():
    activity = parse_activity("# Spesa\n\n## Todo\n- [ ] Pane (integrale)\n- [ ] Latte (2026-13-40)\n", "x")

    assert [(item.text, item.priority, item.due) for item in activity.items] == [("Pane (integrale)", None, None), ("Latte", None, None)]


@pytest.mark.parametrize("name, kind", [
    ("agent-task-refactor.md", NoteType.AGENT_TASK), ("Attivita-rilascio.md", NoteType.ACTIVITY),
    ("todo-list-rilascio.md", NoteType.GENERIC),  # an old todo list, before the migration
    ("decisioni.md", NoteType.GENERIC), ("agent-taskforce.md", NoteType.GENERIC),
])
def test_the_type_of_a_note_is_in_its_name(name, kind):
    assert note_type(name) == kind


def test_typed_notes_are_named_after_their_title():
    assert typed_note_file_name(NoteType.AGENT_TASK, "Refactor del Login!") == "agent-task-refactor-del-login.md"
    assert typed_note_file_name(NoteType.ACTIVITY, "???") == "attivita-senza-titolo.md"


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
    activity = Activity(title="Rilascio", items=[TodoItem(text="tag")], references=["context-reference-procedura.md"])
    assert parse_activity(render_activity(activity), "x") == activity
    assert "## Riferimenti" not in render_agent_task(TASK)  # only when there are some


def test_reference_names_and_hand_written_links():
    assert note_type("code-reference-login.md") is NoteType.CODE_REFERENCE
    assert note_type("context-reference-x.md") is NoteType.CONTEXT_REFERENCE and NoteType.CONTEXT_REFERENCE.is_reference
    assert typed_note_file_name(NoteType.CODE_REFERENCE, "Login OK") == "code-reference-login-ok.md"
    text = "# T\n\n- [ ] voce\n\n## Riferimenti\n* code-reference-a.md\n- [x] non un link\n- code-reference-a.md\n"
    activity = parse_activity(text, "x")
    assert activity.references == ["code-reference-a.md"] and [item.text for item in activity.items] == ["voce"]
