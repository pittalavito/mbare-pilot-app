"""Blocco 05: the Architect's tools: tools and agents, the project's
automations in YAML, the validation of a proposal (nothing saved) and the
agent task for a missing tool. Only in a chatbot's run of a project."""
import pytest

from fakes import as_dict
from models.domain.agent import RunOrigin
from models.domain.project import Project, ProjectSource
from tool.context import ToolContext
from tool.list.architect.tools import LIST_AGENTS, LIST_TOOLS, READ_AUTOMATION, REQUEST_TOOL, VALIDATE_AUTOMATION

PROPOSAL = "name: Stato\nsteps:\n  - {name: Stato, tool: git_status, args: {repository: '*'}}\n"


@pytest.fixture
def run(project_store, pipeline_service, project_data_service, tmp_path):
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path=str(tmp_path)))
    return ToolContext(project_name="acme", git=None, origin=RunOrigin.CHAT, pipelines=pipeline_service,  # type: ignore[arg-type]
                       project_data=project_data_service)


def _call(spec, context, **arguments):
    return as_dict(spec.build(context).func(**arguments))


def test_tools_and_agents(run, agent_config_service):
    tools = _call(LIST_TOOLS, run)["tools"]
    git_log = next(line for line in tools if line.startswith("git_log —"))
    assert "limit (integer, default 20)" in git_log and "repository (string, obbligatorio)" in git_log
    assert not any(line.startswith("delegate_task") for line in tools)  # chat-only: not for a step
    assert isinstance(_call(LIST_AGENTS, run)["agents"], list)


def test_validate_reads_and_never_saves(run, pipeline_service):
    valid = _call(VALIDATE_AUTOMATION, run, yaml=PROPOSAL)
    assert valid == {"valid": True, "error": "", "replaces": False, "steps": ["Stato: tool git_status"],
                     "edges": ["input → Stato"]}
    assert pipeline_service.list_pipelines("acme") == []

    wrong = _call(VALIDATE_AUTOMATION, run, yaml="name: X\nsteps: [{name: S, tool: non_esiste}]")
    assert wrong["valid"] is False and "non esiste" in wrong["error"]

    pipeline_service.save_yaml("acme", PROPOSAL)
    assert _call(VALIDATE_AUTOMATION, run, yaml=PROPOSAL)["replaces"] is True
    conditional = (PROPOSAL + "  - {name: Nota, tool: save_note, args: {content: '{input}'}}\nedges:\n"
                   "  - {from: input, to: Stato}\n  - {from: Stato, to: Nota, if: contains, value: M}\n")
    assert _call(VALIDATE_AUTOMATION, run, yaml=conditional.replace("name: Stato\n", "name: Altra\n", 1))["edges"][1] == "Stato → Nota (contains 'M')"

    read = _call(READ_AUTOMATION, run, name="stato")
    assert read["name"] == "Stato" and "tool: git_status" in read["yaml"]
    assert "non trovata" in _call(READ_AUTOMATION, run, name="manca")["error"]


def test_only_in_a_chatbot(run):
    outside = ToolContext(project_name="acme", git=None, origin=RunOrigin.MANUAL, pipelines=run.pipelines)  # type: ignore[arg-type]
    for spec, arguments in ((LIST_TOOLS, {}), (LIST_AGENTS, {}), (READ_AUTOMATION, {"name": "x"}), (VALIDATE_AUTOMATION, {"yaml": PROPOSAL}),
                            (REQUEST_TOOL, {"title": "t", "objective": "", "criteria": []})):
        assert "solo nel chatbot" in _call(spec, outside, **arguments)["error"]
