"""ask_agent: an agent delegates to another one through AgentService, with fake
agents (no LLM). The delegated run is recorded on its own, inside the parent's
run; a delegated agent cannot delegate again."""
import json
from types import SimpleNamespace

import pytest

from fakes import FakeAgent
from models.domain.agent import AgentConfig, RunOrigin
from models.domain.project import Project, ProjectSource
from service import agent_service as agent_service_module
from service.agent_service import AgentService
from service.chat_service import ChatService
from service.git_service import GitService
from tool.context import ToolContext
from tool.list.agent.ask_agent import ASK_AGENT


class _Delegating:
    """An agent whose run calls its ask_agent tool once and answers with the result."""

    def __init__(self, tools, agent: str, question: str):
        self._tool = next(tool for tool in tools if tool.name == "ask_agent")
        self._agent, self._question = agent, question

    def run(self, task_input, memory=None):
        return SimpleNamespace(text=self._tool.func(agent=self._agent, question=self._question))


@pytest.fixture
def service(store_service, agent_config_service, monkeypatch):
    store_service.save_project(Project(name="acme", source=ProjectSource.FOLDER, root_path="/code/acme"))
    prompt_id = agent_config_service.latest_prompt("hello").id
    for name, project, tools in (("boss", "acme", ["ask_agent"]), ("jira", "acme", ["ask_agent"]), ("other", None, [])):
        agent_config_service.save_config(AgentConfig(
            name=name, project_name=project, description=f"agente {name}", role_name="hello", prompt_id=prompt_id,
            model="openai/gpt-4o", tool_names=tools,
        ), create=True)
    chat = ChatService()
    monkeypatch.setattr(chat, "get_client", lambda model: object())
    return AgentService(chat, agent_config_service, store_service, GitService(store_service))


def _agents(monkeypatch, delegations: dict[str, tuple[str, str]]):
    """``delegations``: agent name -> (agent it asks, question); the others echo."""
    def create_agent(definition, client, tools):
        if definition.name in delegations:
            return _Delegating(tools, *delegations[definition.name])
        return FakeAgent()
    monkeypatch.setattr(agent_service_module.AgentFactory, "create_agent", staticmethod(create_agent))


def test_delegation_runs_the_other_agent_on_the_same_project(service, store_service, monkeypatch):
    _agents(monkeypatch, {"boss": ("jira", "stato di PROJ-1?")})

    record = service.run("boss", "com'è PROJ-1?", project_name="acme")

    answer = json.loads(record.output)
    assert (answer["agent"], answer["answer"]) == ("jira", "echo: stato di PROJ-1?")
    runs = {run.config_name: run for run in store_service.list_runs()}
    assert runs["jira"].origin == RunOrigin.AGENT and runs["jira"].project_name == "acme"
    assert runs["jira"].run_id == answer["run_id"] and runs["boss"].origin == RunOrigin.MANUAL


def test_a_delegated_agent_cannot_delegate_again(service, monkeypatch):
    _agents(monkeypatch, {"boss": ("jira", "chiedi a other"), "jira": ("other", "ciao")})

    record = service.run("boss", "x", project_name="acme")

    nested = json.loads(json.loads(record.output)["answer"])
    assert "già stato chiamato da un altro agente" in nested["error"]


def test_unknown_agent_lists_the_available_ones(service, monkeypatch):
    _agents(monkeypatch, {"boss": ("nessuno", "ciao")})

    error = json.loads(service.run("boss", "x", project_name="acme").output)["error"]

    assert "Agenti disponibili: boss, hello, jira, other" in error


def test_description_lists_the_runnable_agents_of_the_project(service, store_service):
    store_service.set_role_active("hello", False)  # every agent here uses role hello: all blocked
    blocked = ASK_AGENT.build(ToolContext("acme", git=None, agents=service))
    store_service.set_role_active("hello", True)
    built = ASK_AGENT.build(ToolContext("acme", git=None, agents=service))
    outside = ASK_AGENT.build(ToolContext(None, git=None, agents=service))

    assert "- none" in blocked.description
    assert "- jira: agente jira" in built.description and "- other: agente other" in built.description
    assert "jira" not in outside.description and "- other" in outside.description


def test_without_agent_service_there_is_no_delegation():
    built = ASK_AGENT.build(ToolContext("acme", git=None))

    assert "Delega non disponibile" in json.loads(built.func(agent="x", question="y"))["error"]
