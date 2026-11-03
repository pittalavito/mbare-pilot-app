"""The refiner's agent task tools: it takes a task only while created, works
on it in refinement, and makes it todo once refined. Every other move is
refused by the tool, whatever the agent asks."""
import pytest

from fakes import as_dict
from models.domain.agent import RunOrigin
from models.domain.note import AgentTask, ChecklistItem, NoteType, Reference, TaskStatus, TaskType
from models.domain.project import Project, ProjectSource
from tool.context import ToolContext
from tool.list.refiner.agent_tasks import (
    FINISH_REFINEMENT,
    LIST_REFINABLE_TASKS,
    READ_AGENT_TASK,
    START_REFINEMENT,
    UPDATE_AGENT_TASK,
)

GREZZO = "agent-task-grezzo.md"


@pytest.fixture
def context(project_data_service, project_store) -> ToolContext:
    """Chatbot run of «Acme Srl» with one task per status; «Grezzo» links two references (one deleted)."""
    project_store.save(Project(name="Acme Srl", source=ProjectSource.FOLDER, root_path="/code/acme"))
    data = project_data_service
    jira = data.create_reference("Acme Srl", NoteType.CONTEXT_REFERENCE, Reference(
        title="NAV-7 · Login lento", source="jira", source_url="https://acme.atlassian.net/browse/NAV-7", content="Il login ci mette 10 s.",
    ))
    data.create_agent_task("Acme Srl", AgentTask(title="Grezzo", type=TaskType.REFINEMENT, objective="Login veloce",
                                                 references=[jira, "context-reference-sparito.md"]))
    for title, status in (("In lavoro", TaskStatus.REFINEMENT), ("Pronto", TaskStatus.TODO),
                          ("Avviato", TaskStatus.IN_PROGRESS), ("Chiuso", TaskStatus.DONE)):
        data.create_agent_task("Acme Srl", AgentTask(title=title, status=status))
    return ToolContext(project_name="Acme Srl", git=None, origin=RunOrigin.CHAT, project_data=data)


def _call(spec, run, **kwargs):
    return as_dict(spec.build(run).func(**kwargs))


def _update(run, task, **fields):
    return _call(UPDATE_AGENT_TASK, run, task=task, **{"objective": "", "context": "", "criteria": [], "constraints": "", **fields})


def _status(run, name):
    return run.project_data.agent_task("Acme Srl", name).status


def test_only_created_and_refinement_tasks_are_listed(context):
    tasks = _call(LIST_REFINABLE_TASKS, context)["tasks"]

    assert [(task["title"], task["status"]) for task in tasks] == [("Grezzo", "created"), ("In lavoro", "refinement")]


def test_taking_a_created_task_puts_it_in_refinement_and_gives_its_references(context):
    taken = _call(START_REFINEMENT, context, task="agent-task-grezzo")  # .md added

    assert _status(context, GREZZO) == TaskStatus.REFINEMENT
    assert (taken["task"], taken["status"], taken["type"], taken["objective"]) == (GREZZO, "refinement", "refinement", "Login veloce")
    assert taken["references"] == [{
        "name": "context-reference-nav-7-login-lento.md", "title": "NAV-7 · Login lento", "kind": "context", "source": "jira",
        "content": "Il login ci mette 10 s.",
    }]  # the deleted one is left out
    assert taken["link"] == f"/projects/Acme%20Srl/data?note={GREZZO}"
    assert "«in rifinitura»" in _call(START_REFINEMENT, context, task=GREZZO)["error"]  # taken already
    assert _call(READ_AGENT_TASK, context, task=GREZZO) == taken  # now it can read it


@pytest.mark.parametrize("title", ["Pronto", "Avviato", "Chiuso"])
def test_a_task_past_refinement_is_not_the_refiners(context, title):
    name = f"agent-task-{title.lower().replace(' ', '-')}.md"
    before = context.project_data.agent_task("Acme Srl", name)

    for spec, kwargs in ((START_REFINEMENT, {}), (READ_AGENT_TASK, {}), (FINISH_REFINEMENT, {})):
        assert "si può fare solo con un task" in _call(spec, context, task=name, **kwargs)["error"]
    assert "si può fare solo con un task «in rifinitura»" in _update(context, name, objective="altro")["error"]
    assert context.project_data.agent_task("Acme Srl", name) == before  # untouched


def test_a_created_task_must_be_taken_before_working_on_it(context):
    assert "«creato»" in _call(READ_AGENT_TASK, context, task=GREZZO)["error"]
    assert "«creato»" in _update(context, GREZZO, objective="x")["error"]
    assert "«creato»" in _call(FINISH_REFINEMENT, context, task=GREZZO)["error"]  # never straight to todo


def test_updating_writes_the_given_fields_and_leaves_the_others(context):
    _call(START_REFINEMENT, context, task=GREZZO)
    context.project_data.save_agent_task("Acme Srl", GREZZO, context.project_data.agent_task("Acme Srl", GREZZO).model_copy(update={
        "context": "Segnalato dal supporto.", "criteria": [ChecklistItem(text="Login sotto 1 s", done=True)],
    }))

    saved = _update(context, GREZZO, objective="  Login sotto il secondo ", criteria=["Login sotto 1 s", " ", "Test di carico"],
                    constraints="Non cambiare lo schema del DB.")

    assert (saved["objective"], saved["context"], saved["constraints"]) == (
        "Login sotto il secondo", "Segnalato dal supporto.", "Non cambiare lo schema del DB.",
    )
    task = context.project_data.agent_task("Acme Srl", GREZZO)
    assert [(item.text, item.done) for item in task.criteria] == [("Login sotto 1 s", True), ("Test di carico", False)]  # ticks kept
    assert (task.title, task.type, task.status) == ("Grezzo", TaskType.REFINEMENT, TaskStatus.REFINEMENT)  # the user's

    unchanged = _update(context, GREZZO)
    assert unchanged["criteria"] == ["Login sotto 1 s", "Test di carico"] and unchanged["objective"] == "Login sotto il secondo"


def test_finishing_needs_objective_and_criteria_then_makes_it_todo(context):
    name = "agent-task-in-lavoro.md"
    assert "mancano l'obiettivo e i criteri di accettazione" in _call(FINISH_REFINEMENT, context, task=name)["error"]
    _update(context, name, objective="Fare qualcosa")
    assert "mancano i criteri di accettazione" in _call(FINISH_REFINEMENT, context, task=name)["error"]
    assert _status(context, name) == TaskStatus.REFINEMENT

    _update(context, name, criteria=["Fatto bene"])
    done = _call(FINISH_REFINEMENT, context, task=name)

    assert done["status"] == "todo" and _status(context, name) == TaskStatus.TODO
    assert "si può fare solo con un task «in rifinitura»" in _update(context, name, objective="ancora")["error"]  # no longer its


def test_unknown_tasks_and_runs_outside_a_chatbot(context):
    assert "not found" in _call(READ_AGENT_TASK, context, task="agent-task-manca.md")["error"].lower()
    assert "non è un agent task" in _call(START_REFINEMENT, context, task="appunti.md")["error"]

    outside = ToolContext(project_name="Acme Srl", git=None, origin=RunOrigin.MANUAL, project_data=context.project_data)
    for spec, kwargs in ((LIST_REFINABLE_TASKS, {}), (START_REFINEMENT, {"task": GREZZO}), (READ_AGENT_TASK, {"task": GREZZO}),
                         (FINISH_REFINEMENT, {"task": GREZZO})):
        assert "solo nel chatbot di un progetto" in _call(spec, outside, **kwargs)["error"]
    assert "solo nel chatbot di un progetto" in _update(outside, GREZZO)["error"]
    assert _status(context, GREZZO) == TaskStatus.CREATED
