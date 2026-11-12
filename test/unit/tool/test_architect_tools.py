"""Blocco 05: the Architect's tools: functions and agents, the project's
automations in YAML, the validation of a proposal (nothing saved) and the
agent task for a missing function. Only in a chatbot's run of a project."""
import pytest

from fakes import as_dict
from models.domain.agent import RunOrigin
from models.domain.note import Activity
from models.domain.project import Project, ProjectSource
from tool.context import ToolContext
from tool.list.architect.tools import CREATE_FUNCTION_TASK, LIST_AGENTS, LIST_FUNCTIONS, READ_AUTOMATION, VALIDATE_AUTOMATION

PROPOSAL = "name: Stato\nsteps:\n  - {name: Stato, function: git_status, params: {repository: '*'}}\n"


@pytest.fixture
def run(project_store, pipeline_service, project_data_service, tmp_path):
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path=str(tmp_path)))
    return ToolContext(project_name="acme", git=None, origin=RunOrigin.CHAT, pipelines=pipeline_service,  # type: ignore[arg-type]
                       project_data=project_data_service)


def _call(spec, context, **arguments):
    return as_dict(spec.build(context).func(**arguments))


def test_functions_and_agents(run, agent_config_service):
    functions = _call(LIST_FUNCTIONS, run)["functions"]
    git_log = next(line for line in functions if line.startswith("git_log —"))
    assert "limit (int, default 20)" in git_log
    assert next(line for line in functions if line.startswith("git_check_clean")).endswith("nessun parametro")
    assert isinstance(_call(LIST_AGENTS, run)["agents"], list)


def test_validate_reads_and_never_saves(run, pipeline_service):
    valid = _call(VALIDATE_AUTOMATION, run, yaml=PROPOSAL)
    assert valid == {"valid": True, "error": "", "replaces": False, "system": False, "steps": ["Stato: funzione git_status"],
                     "edges": ["input → Stato"]}
    assert pipeline_service.list_pipelines("acme") == []

    wrong = _call(VALIDATE_AUTOMATION, run, yaml="name: X\nsteps: [{name: S, function: non_esiste}]")
    assert wrong["valid"] is False and "non esiste" in wrong["error"]

    pipeline_service.save_yaml("acme", PROPOSAL)
    assert _call(VALIDATE_AUTOMATION, run, yaml=PROPOSAL)["replaces"] is True
    assert _call(VALIDATE_AUTOMATION, run, yaml=PROPOSAL.replace("name: Stato\n", "name: Verifica sviluppo\n", 1))["system"] is True
    conditional = (PROPOSAL + "  - {name: Nota, function: save_note}\nedges:\n"
                   "  - {from: input, to: Stato}\n  - {from: Stato, to: Nota, if: contains, value: M}\n")
    assert _call(VALIDATE_AUTOMATION, run, yaml=conditional.replace("name: Stato\n", "name: Altra\n", 1))["edges"][1] == "Stato → Nota (contains 'M')"

    read = _call(READ_AUTOMATION, run, name="stato")
    assert read["name"] == "Stato" and "function: git_status" in read["yaml"]
    assert "non trovata" in _call(READ_AUTOMATION, run, name="manca")["error"]


def test_a_task_for_a_missing_function(run, project_data_service):
    activity = project_data_service.create_activity("acme", Activity(title="Rilascio"))

    created = _call(CREATE_FUNCTION_TASK, run, title="Funzione git_tag", objective="Crea un tag.", criteria=["Test", " "], activity=activity)

    task = project_data_service.agent_task("acme", created["task"])
    assert (task.status.value, task.type.value, [item.text for item in task.criteria]) == ("refinement", "development", ["Test"])
    assert project_data_service.activity("acme", activity).agent_tasks == [created["task"]]
    assert created["link"].endswith(created["task"])
    assert "not found" in _call(CREATE_FUNCTION_TASK, run, title="Altra", objective="", criteria=[], activity="attivita-manca").get("error", "").lower()
    assert _call(CREATE_FUNCTION_TASK, run, title=" ", objective="", criteria=[])["error"] == "Serve un titolo."


def test_only_in_a_chatbot(run):
    outside = ToolContext(project_name="acme", git=None, origin=RunOrigin.MANUAL, pipelines=run.pipelines)  # type: ignore[arg-type]
    for spec, arguments in ((LIST_FUNCTIONS, {}), (LIST_AGENTS, {}), (READ_AUTOMATION, {"name": "x"}), (VALIDATE_AUTOMATION, {"yaml": PROPOSAL}),
                            (CREATE_FUNCTION_TASK, {"title": "t", "objective": "", "criteria": []})):
        assert "solo nel chatbot" in _call(spec, outside, **arguments)["error"]
