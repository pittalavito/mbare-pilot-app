"""Plan 15, one registry: the function steps of before become tool steps (on
read, saved at startup), the run history of function steps reads as tool steps,
the Architect's old tool names are renamed, and a tool can be tried by hand."""
from datetime import datetime, timezone

import pytest
from datapizza.tools import Tool
from sqlmodel import Session, select

from core.container import Container
from core.error import NotFoundError, ValidationError
from domain.pipeline.legacy import function_as_tool
from models.domain.chatbot import Chatbot, ChatbotKind
from models.domain.pipeline import PipelineRun, RunStatus, StepKind
from models.domain.project import Project, ProjectSource
from models.store.db import PipelineStepRunTable, PipelineStepTable, PipelineTable
from tool.registry import TOOL_REGISTRY
from tool.spec import ToolSpec


@pytest.mark.parametrize("function, params, tool, args", [
    ("git_status", {"repository": "*"}, "git_status", {"repository": "*"}),
    ("git_status", {}, "git_status", {"repository": "{input}"}),
    ("git_log", {"limit": 5}, "git_log", {"limit": 5, "repository": "{input}"}),
    ("git_pull_all_repo_by_branch", {}, "git_pull_all_by_branch", {"branch": "{input}"}),
    ("git_pull_all_repo_by_branch", {"branch": "develop"}, "git_pull_all_by_branch", {"branch": "develop"}),
    ("git_pull_repo_by_branch", {"branch": "main"}, "git_pull_by_branch", {"branch": "main", "repository": "{input}"}),
    ("git_pull_repo_by_branch", {"repository": "api"}, "git_pull_by_branch", {"repository": "api"}),
    ("save_note", {"title": "x"}, "save_note", {"title": "x", "content": "{input}"}),
    ("git_check_clean", {}, "git_check_clean", {"targets": "{pipeline_input}"}),
    ("run_tests", {"timeout_minutes": 5}, "run_tests", {"timeout_minutes": 5, "target": "{pipeline_input}"}),
    ("maven_parent_alignment", {"property": "p"}, "maven_parent_alignment", {"property": "p"}),
])
def test_a_function_becomes_its_tool(function, params, tool, args):
    assert function_as_tool(function, params) == (tool, args)
    assert set(args) <= set(TOOL_REGISTRY[tool].schema()[0])


@pytest.fixture
def legacy(stores, project_store, tmp_path):
    """An automation saved before plan 15: a function step and a run of it in the history."""
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path=str(tmp_path)))
    with Session(stores.engine) as session:
        now = datetime.now(timezone.utc)
        pipeline = PipelineTable(project_name="acme", name="Vecchia", purpose="", created_at=now, updated_at=now)
        session.add(pipeline)
        session.commit()
        session.refresh(pipeline)
        session.add(PipelineStepTable(pipeline_id=pipeline.id, position=0, name="Nota", kind="function", function_name="save_note",
                                      params={"title": "x"}))
        session.commit()
        pipeline_id = pipeline.id
    run = stores.pipelines.save_pipeline_run(PipelineRun(pipeline_id=pipeline_id, status=RunStatus.DONE))
    with Session(stores.engine) as session:
        session.add(PipelineStepRunTable(pipeline_run_id=run.id, position=0, name="Nota", kind="function", status="done", output="ok"))
        session.commit()
    return pipeline_id, run.id


def test_the_old_function_steps_read_as_tool_steps_and_are_saved_so_at_startup(stores, legacy):
    pipeline_id, run_id = legacy
    [step] = stores.pipelines.get_pipeline(pipeline_id).steps
    assert (step.kind, step.tool_name, step.params) == (StepKind.TOOL, "save_note", {"title": "x", "content": "{input}"})
    assert stores.pipelines.get_pipeline_run(run_id).steps[0].kind is StepKind.TOOL  # the history too

    Container(stores=stores)  # the startup conversion
    with Session(stores.engine) as session:
        row = session.exec(select(PipelineStepTable).where(PipelineStepTable.pipeline_id == pipeline_id)).one()
    assert (row.kind, row.tool_name, row.function_name) == ("tool", "save_note", None)
    assert stores.pipelines.convert_function_steps() == 0  # once


def test_the_architects_old_tool_names_are_renamed_at_startup(stores, project_store, tmp_path):
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path=str(tmp_path)))
    stores.chatbots.save_chatbot(Chatbot(project_name="acme", name="Architetto", kind=ChatbotKind.AUTOMATION, system_prompt="x",
                                         model="openai/gpt-4o", tool_names=["list_functions", "list_agents", "create_function_task"]))
    Container(stores=stores)
    [bot] = stores.chatbots.list_chatbots("acme")
    assert bot.tool_names == ["list_tools", "list_agents", "create_tool_task"]


def test_a_yaml_step_with_function_says_how_to_write_it_now(pipeline_service, project_store, tmp_path):
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path=str(tmp_path)))
    with pytest.raises(ValidationError, match="scrivi «tool: git_status» con «args:»"):
        pipeline_service.check_yaml("acme", "name: X\nsteps: [{name: S, function: git_status, params: {repository: api}}]")


def test_trying_a_tool_by_hand(stores, project_store, tmp_path, monkeypatch):
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path=str(tmp_path)))
    container = Container(stores=stores)
    service = container.agent_service

    assert service.try_tool("save_note", "acme", {"title": "Prova", "content": "ciao"}).text.startswith("Nota salvata")
    assert "Argomenti non validi" in service.try_tool("hello_world", "acme", {"nome": "x"}).error
    assert service.try_tool("hello_world", "acme", {"name": "Ada"}).response == "Hello, Ada!"
    with pytest.raises(NotFoundError):
        service.try_tool("nessuno", "acme", {})

    plain = Tool(func=lambda: "solo testo", name="plain", description="x", properties={}, required=[])
    monkeypatch.setitem(TOOL_REGISTRY, "plain", ToolSpec("plain", "x", lambda context: plain))
    assert service.try_tool("plain", "acme", {}).text == "solo testo"

    def boom():
        raise ValidationError("rotto")
    broken = Tool(func=boom, name="broken", description="x", properties={}, required=[])
    monkeypatch.setitem(TOOL_REGISTRY, "broken", ToolSpec("broken", "x", lambda context: broken))
    assert service.try_tool("broken", "acme", {}).error == "rotto"
