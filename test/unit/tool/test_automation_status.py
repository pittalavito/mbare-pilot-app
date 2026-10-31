"""automation_status: only the statuses of a run of one of the project's
automations and of its steps, never its output or errors (fake agents, no
LLM). Runs of other projects are not found; only in a chatbot's run."""

import pytest

from fakes import FakeAgent, as_dict
from models.domain.agent import RunOrigin
from models.domain.pipeline import PipelineStep, StepAgent, StepKind
from models.domain.project import Project, ProjectSource
from service import agent_service as agent_service_module
from service.chat_service import ChatService
from service.git_service import GitService
from service.pipeline_runner import PipelineRunner
from service.pipeline_service import PipelineService
from service.project_data_service import ProjectDataService
from tool.context import ToolContext
from tool.list.automation.automation_status import AUTOMATION_STATUS

MODEL = "openai/gpt-4o"


@pytest.fixture
def pipelines(store_service, agent_config_service, worker_store):
    for name in ("acme", "other"):
        store_service.save_project(Project(name=name, source=ProjectSource.FOLDER, root_path=f"/code/{name}"))
    return PipelineService(store_service, agent_config_service, worker_store)


@pytest.fixture
def runner(store_service, pipelines, monkeypatch, make_agent_service):
    chat = ChatService()
    monkeypatch.setattr(chat, "get_client", lambda model: object())
    monkeypatch.setattr(agent_service_module.AgentFactory, "create_agent",
                        staticmethod(lambda definition, client, tools: FakeAgent()))
    agents = make_agent_service(chat, pipeline_service=pipelines)
    return PipelineRunner(store_service, agents, GitService(store_service), ProjectDataService(store_service))


def _automation(pipelines, project="acme"):
    step = PipelineStep(name="Analizza", kind=StepKind.AGENT, agent=StepAgent(system_prompt="Fai.", model=MODEL))
    return pipelines.create_pipeline(project, "Report", steps=[step])


def _status(pipelines, run_id, project="acme", origin=RunOrigin.CHAT):
    context = ToolContext(project, git=None, pipelines=pipelines, origin=origin)
    return as_dict(AUTOMATION_STATUS.build(context).func(run_id=run_id))


def test_queued_then_done_only_statuses(pipelines, runner):
    run = pipelines.enqueue(_automation(pipelines).id, "ciao")

    assert _status(pipelines, run.id) == {"automation": "Report", "run_id": run.id, "status": "queued", "steps": []}

    runner.run_next()

    assert _status(pipelines, run.id) == {
        "automation": "Report", "run_id": run.id, "status": "done", "steps": [{"name": "Analizza", "status": "done"}],
    }


def test_runs_of_other_projects_or_unknown_are_not_found(pipelines):
    run = pipelines.enqueue(_automation(pipelines, "other").id)

    assert "non trovata" in _status(pipelines, run.id)["error"]
    assert "non trovata" in _status(pipelines, 999)["error"]


def test_only_in_a_chatbots_run_of_a_project(pipelines):
    run = pipelines.enqueue(_automation(pipelines).id)

    for answer in (_status(pipelines, run.id, project=None), _status(pipelines, run.id, origin=RunOrigin.MANUAL),
                   _status(pipelines, run.id, origin=RunOrigin.PIPELINE)):
        assert "solo nel chatbot" in answer["error"]

