"""run_automation: the chatbot of a project queues one of the project's
automations and gets the run id back at once (fake agents, no LLM). Only in a
chatbot's run: never from a manual run, from inside an automation or outside
a project."""
import json
from types import SimpleNamespace

import pytest

from fakes import FakeAgent, as_dict
from models.domain.agent import AgentConfig, RunOrigin
from models.domain.pipeline import PipelineStep, RunStatus, StepAgent, StepKind
from models.domain.project import Project, ProjectSource
from service import agent_service as agent_service_module
from service.chat_service import ChatService
from service.pipeline_runner import PipelineRunner
from tool.context import ToolContext
from tool.list.automation.list_automations import LIST_AUTOMATIONS
from tool.list.automation.run_automation import RUN_AUTOMATION

MODEL = "openai/gpt-4o"


class _Launching:
    """An agent whose run calls its run_automation tool once and answers with the result."""

    def __init__(self, tools, automation: str, task: str = "ciao"):
        self._tool = next(tool for tool in tools if tool.name == "run_automation")
        self._automation, self._task = automation, task

    def run(self, task_input, memory=None):
        return SimpleNamespace(text=self._tool.func(automation=self._automation, input=self._task))


@pytest.fixture
def pipelines(store_service, pipeline_service):
    store_service.save_project(Project(name="acme", source=ProjectSource.FOLDER, root_path="/code/acme"))
    return pipeline_service


@pytest.fixture
def service(agent_config_service, pipelines, monkeypatch, make_agent_service):
    agent_config_service.save_config(AgentConfig(
        name="boss", project_name="acme", role_name="hello", prompt_id=agent_config_service.latest_prompt("hello").id,
        model=MODEL, tool_names=["run_automation"],
    ), create=True)
    chat = ChatService()
    monkeypatch.setattr(chat, "get_client", lambda model: object())
    return make_agent_service(chat, pipeline_service=pipelines)


def _own_step(tools=()):
    return PipelineStep(name="S", kind=StepKind.AGENT, agent=StepAgent(system_prompt="Fai.", model=MODEL, tool_names=list(tools)))


def _agents(monkeypatch, launches: dict[str, str]):
    """``launches``: agent name -> automation it starts; the others echo."""
    def create_agent(definition, client, tools):
        for prefix, automation in launches.items():
            if definition.name.startswith(prefix):
                return _Launching(tools, automation)
        return FakeAgent()
    monkeypatch.setattr(agent_service_module.AgentFactory, "create_agent", staticmethod(create_agent))


def test_queues_the_run_and_answers_at_once(service, pipelines, monkeypatch):
    report = pipelines.create_pipeline("acme", "Report", description="report del giorno", steps=[_own_step()])
    _agents(monkeypatch, {"boss": "Report"})

    answer = json.loads(service.run("boss", "lancia il report", project_name="acme", origin=RunOrigin.CHAT).output)

    [run] = pipelines.list_runs(report.id)
    assert answer == {"automation": "Report", "run_id": run.id, "status": "queued"}
    assert (run.status, run.input) == (RunStatus.QUEUED, "ciao")


def test_only_runnable_automations_start_and_the_description_lists_none(service, pipelines):
    pipelines.create_pipeline("acme", "Report", description="report del giorno", steps=[_own_step()])
    pipelines.create_pipeline("acme", "Spenta", active=False, steps=[_own_step()])

    built = RUN_AUTOMATION.build(ToolContext("acme", git=None, pipelines=pipelines, origin=RunOrigin.CHAT))

    assert "Report" not in built.description and "list_automations" in built.description
    assert "Disponibili: Report" in as_dict(built.func(automation="Spenta", input=""))["error"]


def test_unknown_automation_lists_the_available_ones(service, pipelines, monkeypatch):
    pipelines.create_pipeline("acme", "Report", steps=[_own_step()])
    _agents(monkeypatch, {"boss": "Altro"})

    error = json.loads(service.run("boss", "x", project_name="acme", origin=RunOrigin.CHAT).output)["error"]

    assert "Disponibili: Report" in error


@pytest.mark.parametrize("context", [
    ToolContext(None, git=None, origin=RunOrigin.CHAT),  # outside a project
    ToolContext("acme", git=None),  # a manual run, not the chatbot
    ToolContext("acme", git=None, origin=RunOrigin.PIPELINE),  # inside an automation
])
def test_only_in_a_chatbots_run_of_a_project(pipelines, context):
    pipelines.create_pipeline("acme", "Report", steps=[_own_step()])
    built = RUN_AUTOMATION.build(ToolContext(**{**context.__dict__, "pipelines": pipelines}))

    assert "non disponibili" in as_dict(built.func(automation="Report", input=""))["error"]


def test_an_automation_cannot_start_automations(service, store_service, pipelines, monkeypatch, git_service, project_data_service):
    """A step agent with run_automation, run by the worker: the tool refuses, nothing new is queued."""
    loop = pipelines.create_pipeline("acme", "Loop", steps=[_own_step(tools=["run_automation"])])
    _agents(monkeypatch, {"pipeline/": "Loop"})
    pipelines.enqueue(loop.id)
    runner = PipelineRunner(store_service, service, git_service, project_data_service)

    run = runner.run_next()

    assert run.status is RunStatus.DONE and "non disponibili" in run.output
    assert len(pipelines.list_runs(loop.id)) == 1


def test_list_automations_only_the_runnable_ones_only_in_a_chatbot(pipelines):
    pipelines.create_pipeline("acme", "Report", description="report del giorno", steps=[_own_step()])
    pipelines.create_pipeline("acme", "Spenta", active=False, steps=[_own_step()])
    pipelines.create_pipeline("acme", "Vuota")

    def listed(context):
        return as_dict(LIST_AUTOMATIONS.build(ToolContext(**{**context.__dict__, "pipelines": pipelines})).func())

    assert listed(ToolContext("acme", git=None, origin=RunOrigin.CHAT)) == {
        "automations": [{"name": "Report", "description": "report del giorno"}],
    }
    assert "solo nel chatbot" in listed(ToolContext("acme", git=None))["error"]
