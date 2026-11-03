"""The secretary's agent task tools: the references by title only, and a new
agent task born in refinement, linked to references that exist. Only in a
chatbot's run of a project."""
import json

import pytest

from fakes import as_dict
from models.domain.agent import RunOrigin
from models.domain.note import NoteType, Reference, TaskStatus, TaskType
from models.domain.project import Project, ProjectSource
from tool.context import ToolContext
from tool.list.notes.agent_tasks import CREATE_AGENT_TASK, LIST_REFERENCES

SECRET = "token di produzione: abc123"


@pytest.fixture
def context(project_data_service, project_store) -> ToolContext:
    """Chatbot run of «Acme Srl» with a code and a context reference."""
    project_store.save(Project(name="Acme Srl", source=ProjectSource.FOLDER, root_path="/code/acme"))
    data = project_data_service
    data.create_reference("Acme Srl", NoteType.CODE_REFERENCE, Reference(title="Login", path="src/login.py", content=SECRET))
    data.create_reference("Acme Srl", NoteType.CONTEXT_REFERENCE, Reference(title="Procedura di rilascio", content=SECRET))
    return ToolContext(project_name="Acme Srl", git=None, origin=RunOrigin.CHAT, project_data=data)


def _call(spec, run, **kwargs):
    return as_dict(spec.build(run).func(**kwargs))


def _create(run, **fields):
    values = {"title": "Rilascio automatico", "type": TaskType.DEVELOPMENT, "objective": "", "context": "", "criteria": [],
              "constraints": "", "references": [], "activity": "", **fields}
    return _call(CREATE_AGENT_TASK, run, **values)


def test_the_references_by_title_never_their_content(context):
    result = _call(LIST_REFERENCES, context)

    assert result == {"references": [
        {"name": "code-reference-login.md", "title": "Login", "kind": "code"},
        {"name": "context-reference-procedura-di-rilascio.md", "title": "Procedura di rilascio", "kind": "context"},
    ]}
    assert SECRET not in json.dumps(result)


def test_a_new_task_is_in_refinement_with_its_fields_and_references(context):
    result = _create(
        context, title="  Rilascio automatico ", type=TaskType.ANALYSIS, objective="Capire come rilasciare da solo.",
        context="Dall'attività Rilascio, voce 2.", criteria=["Passi documentati", " ", "Rischi elencati"],
        constraints="Non toccare la pipeline.", references=["context-reference-procedura-di-rilascio", "code-reference-login.md",
                                                            "code-reference-login.md"],
    )

    assert result == {
        "task": "agent-task-rilascio-automatico.md", "title": "Rilascio automatico", "type": "analysis", "status": "refinement",
        "references": ["context-reference-procedura-di-rilascio.md", "code-reference-login.md"],  # .md added, once each
        "activity": None,
        "link": "/projects/Acme%20Srl/data?note=agent-task-rilascio-automatico.md",
    }
    task = context.project_data.agent_task("Acme Srl", result["task"])
    assert (task.status, task.type, task.objective, task.context, task.constraints) == (
        TaskStatus.REFINEMENT, TaskType.ANALYSIS, "Capire come rilasciare da solo.", "Dall'attività Rilascio, voce 2.", "Non toccare la pipeline.",
    )
    assert [(item.text, item.done) for item in task.criteria] == [("Passi documentati", False), ("Rischi elencati", False)]


def test_wrong_references_titles_and_names_are_refused(context):
    assert "Riferimenti inesistenti: code-reference-inventato.md" in _create(context, references=["code-reference-inventato.md"])["error"]
    assert "Riferimenti inesistenti: agent-task-altro.md" in _create(context, references=["agent-task-altro.md"])["error"]
    assert "titolo" in _create(context, title="  ")["error"]
    assert context.project_data.agent_tasks("Acme Srl") == []  # nothing created

    _create(context)
    assert "Esiste già" in _create(context)["error"]  # same title


@pytest.mark.parametrize("spec", [LIST_REFERENCES, CREATE_AGENT_TASK])
def test_only_in_a_chatbots_run_of_a_project(context, spec):
    kwargs = {} if spec is LIST_REFERENCES else {
        "title": "x", "type": TaskType.DEVELOPMENT, "objective": "", "context": "", "criteria": [], "constraints": "", "references": [],
        "activity": "",
    }
    for other in (
        ToolContext(project_name="Acme Srl", git=None, origin=RunOrigin.MANUAL, project_data=context.project_data),
        ToolContext(project_name=None, git=None, origin=RunOrigin.CHAT, project_data=context.project_data),
        ToolContext(project_name="Acme Srl", git=None, origin=RunOrigin.CHAT),
    ):
        assert "solo nel chatbot di un progetto" in _call(spec, other, **kwargs)["error"]


def test_an_unknown_project_comes_back_as_an_error(context):
    other = ToolContext(project_name="Manca", git=None, origin=RunOrigin.CHAT, project_data=context.project_data)

    assert "error" in _call(LIST_REFERENCES, other)
    assert "error" in _create(other)


def test_a_task_born_from_an_activity_is_linked_to_it(context):
    from models.domain.note import Activity

    activity = context.project_data.create_activity("Acme Srl", Activity(title="Rilascio"))

    result = _create(context, title="Note di rilascio", activity="attivita-rilascio")

    assert result["activity"] == activity
    assert context.project_data.activity("Acme Srl", activity).agent_tasks == [result["task"]]
    assert "not found" in _create(context, title="Orfano", activity="attivita-manca.md")["error"].lower()
    assert [name for name, _ in context.project_data.agent_tasks("Acme Srl")] == [result["task"]]  # the orphan was not created
