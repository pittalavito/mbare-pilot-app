"""The refiner's agent task tools: they work only on the task open next to the
chat, only while it is in refinement, and make it todo once refined. Every
other move is refused by the tool, whatever the agent asks."""
from dataclasses import replace

import pytest

from core.error import ValidationError
from fakes import as_dict
from models.domain.agent import RunOrigin
from models.domain.copilot import CodingAgentSettings
from models.domain.note import AgentTask, ChecklistItem, NoteType, Reference, TaskStatus, TaskType
from models.domain.project import Project, ProjectSource
from tool.context import ToolContext
from tool.list.refiner.agent_tasks import FINISH_REFINEMENT, READ_AGENT_TASK, UPDATE_AGENT_TASK

GREZZO = "agent-task-grezzo.md"
IN_LAVORO = "agent-task-in-lavoro.md"


class _Copilot:
    """The coding-agent definition's checklists, as CopilotService gives them."""

    def __init__(self, checklists: dict[TaskType, list[str]] | None = None, error: bool = False):
        self._checklists = checklists or {}
        self._error = error

    def coding_agent(self, project_name: str | None = None) -> CodingAgentSettings:
        if self._error:
            raise ValidationError("definizione rotta")
        return CodingAgentSettings(plan_prompt="{task_folder}", execute_prompt="vai", denied_tools=[], task_checklists=self._checklists)


@pytest.fixture
def context(project_data_service, project_store) -> ToolContext:
    """Chatbot run of «Acme Srl» with one task per status; «In lavoro» (a Jira
    task in refinement) links two references (one deleted). No task open yet."""
    project_store.save(Project(name="Acme Srl", source=ProjectSource.FOLDER, root_path="/code/acme"))
    data = project_data_service
    jira = data.create_reference("Acme Srl", NoteType.CONTEXT_REFERENCE, Reference(
        title="NAV-7 · Login lento", source="jira", source_url="https://acme.atlassian.net/browse/NAV-7", content="Il login ci mette 10 s.",
    ))
    data.create_agent_task("Acme Srl", AgentTask(title="Grezzo"))
    data.create_agent_task("Acme Srl", AgentTask(title="In lavoro", status=TaskStatus.REFINEMENT, type=TaskType.JIRA, objective="Login veloce",
                                                 references=[jira, "context-reference-sparito.md"]))
    for title, status in (("Pronto", TaskStatus.TODO), ("Avviato", TaskStatus.IN_PROGRESS),
                          ("Da verificare", TaskStatus.TO_VERIFY), ("Chiuso", TaskStatus.DONE)):
        data.create_agent_task("Acme Srl", AgentTask(title=title, status=status))
    copilot = _Copilot({TaskType.JIRA: ["chiave della issue", "criteri attesi"], TaskType.DEVELOPMENT: ["repository"]})
    return ToolContext(project_name="Acme Srl", git=None, origin=RunOrigin.CHAT, project_data=data, copilot=copilot)  # type: ignore[arg-type]


def _open(run: ToolContext, note: str | None) -> ToolContext:
    return replace(run, open_note=note)


def _call(spec, run, **kwargs):
    return as_dict(spec.build(run).func(**kwargs))


def _update(run, **fields):
    return _call(UPDATE_AGENT_TASK, run, **{"objective": "", "context": "", "criteria": [], "constraints": "", **fields})


def _status(run, name):
    return run.project_data.agent_task("Acme Srl", name).status


def test_reading_the_open_task_gives_its_references_and_its_types_checklist(context):
    run = _open(context, "agent-task-in-lavoro")  # .md added

    task = _call(READ_AGENT_TASK, run)

    assert (task["task"], task["status"], task["type"], task["objective"]) == (IN_LAVORO, "refinement", "jira", "Login veloce")
    assert task["references"] == [{
        "name": "context-reference-nav-7-login-lento.md", "title": "NAV-7 · Login lento", "kind": "context", "source": "jira",
        "content": "Il login ci mette 10 s.",
    }]  # the deleted one is left out
    assert task["checklist"] == ["chiave della issue", "criteri attesi"]  # only its type's
    assert task["link"] == f"/projects/Acme%20Srl/data?note={IN_LAVORO}"


def test_no_checklist_when_the_type_has_none_or_the_definition_cannot_be_read(context):
    run = _open(context, IN_LAVORO)
    assert _call(READ_AGENT_TASK, replace(run, copilot=_Copilot({TaskType.DEVELOPMENT: ["repository"]})))["checklist"] == []
    assert _call(READ_AGENT_TASK, replace(run, copilot=_Copilot(error=True)))["checklist"] == []
    assert _call(READ_AGENT_TASK, replace(run, copilot=None))["checklist"] == []


@pytest.mark.parametrize("note", [None, "appunti.md", "attivita-rilascio.md"])
def test_without_an_open_agent_task_nothing_is_done(context, note):
    run = _open(context, note)

    for spec in (READ_AGENT_TASK, FINISH_REFINEMENT):
        assert "Nessun agent task aperto" in _call(spec, run)["error"]
    assert "Nessun agent task aperto" in _update(run, objective="x")["error"]


def test_a_created_task_must_be_moved_to_refinement_by_the_user(context):
    run = _open(context, GREZZO)

    for spec in (READ_AGENT_TASK, FINISH_REFINEMENT):
        assert "«Rifinisci con il Refiner»" in _call(spec, run)["error"]
    assert "«creato»" in _update(run, objective="x")["error"]
    assert _status(context, GREZZO) == TaskStatus.CREATED  # never straight to todo


@pytest.mark.parametrize("title", ["Pronto", "Avviato", "Da verificare", "Chiuso"])
def test_a_task_past_refinement_is_not_the_refiners(context, title):
    name = f"agent-task-{title.lower().replace(' ', '-')}.md"
    run = _open(context, name)
    before = context.project_data.agent_task("Acme Srl", name)

    for spec in (READ_AGENT_TASK, FINISH_REFINEMENT):
        assert "non è più tuo" in _call(spec, run)["error"]
    assert "non è più tuo" in _update(run, objective="altro")["error"]
    assert context.project_data.agent_task("Acme Srl", name) == before  # untouched


def test_updating_writes_the_given_fields_and_leaves_the_others(context):
    run = _open(context, IN_LAVORO)
    context.project_data.save_agent_task("Acme Srl", IN_LAVORO, context.project_data.agent_task("Acme Srl", IN_LAVORO).model_copy(update={
        "context": "Segnalato dal supporto.", "criteria": [ChecklistItem(text="Login sotto 1 s", done=True)],
    }))

    saved = _update(run, objective="  Login sotto il secondo ", criteria=["Login sotto 1 s", " ", "Test di carico"],
                    constraints="Non cambiare lo schema del DB.")

    assert (saved["objective"], saved["context"], saved["constraints"]) == (
        "Login sotto il secondo", "Segnalato dal supporto.", "Non cambiare lo schema del DB.",
    )
    task = context.project_data.agent_task("Acme Srl", IN_LAVORO)
    assert [(item.text, item.done) for item in task.criteria] == [("Login sotto 1 s", True), ("Test di carico", False)]  # ticks kept
    assert (task.title, task.type, task.status) == ("In lavoro", TaskType.JIRA, TaskStatus.REFINEMENT)  # the user's

    unchanged = _update(run)
    assert unchanged["criteria"] == ["Login sotto 1 s", "Test di carico"] and unchanged["objective"] == "Login sotto il secondo"


def test_finishing_needs_objective_and_criteria_then_makes_it_todo(context):
    context.project_data.save_agent_task("Acme Srl", IN_LAVORO, AgentTask(title="In lavoro", status=TaskStatus.REFINEMENT))
    run = _open(context, IN_LAVORO)
    assert "mancano l'obiettivo e i criteri di accettazione" in _call(FINISH_REFINEMENT, run)["error"]
    _update(run, objective="Fare qualcosa")
    assert "mancano i criteri di accettazione" in _call(FINISH_REFINEMENT, run)["error"]
    assert _status(context, IN_LAVORO) == TaskStatus.REFINEMENT

    _update(run, criteria=["Fatto bene"])
    done = _call(FINISH_REFINEMENT, run)

    assert done["status"] == "todo" and _status(context, IN_LAVORO) == TaskStatus.TODO
    assert "non è più tuo" in _update(run, objective="ancora")["error"]  # no longer its


def test_a_missing_open_task_and_runs_outside_a_chatbot(context):
    assert "not found" in _call(READ_AGENT_TASK, _open(context, "agent-task-manca.md"))["error"].lower()

    outside = replace(context, origin=RunOrigin.MANUAL, open_note=IN_LAVORO)
    for spec in (READ_AGENT_TASK, FINISH_REFINEMENT):
        assert "solo nel chatbot di un progetto" in _call(spec, outside)["error"]
    assert "solo nel chatbot di un progetto" in _update(outside)["error"]
    assert _status(context, IN_LAVORO) == TaskStatus.REFINEMENT
