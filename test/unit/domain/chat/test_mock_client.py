"""The mock model (``mock/echo``): a real datapizza Agent run end-to-end with no
LLM. It echoes, calls a tool on ``/tool name {json}`` and then replies with
its result; tokens are estimated, the cost is 0."""
import pytest

from domain.chat.base import Factory
from domain.chat.mock_client import MockClient
from models.domain.agent import AgentConfig
from service.agent_service import AgentService
from service.chat_service import ChatService
from service.git_service import GitService

MOCK = "mock/echo"


@pytest.fixture
def agents(store_service, agent_config_service):
    agent_config_service.save_config(AgentConfig(
        name="prova", role_name="hello", prompt_id=agent_config_service.latest_prompt("hello").id,
        model=MOCK, tool_names=["hello_world"],
    ), create=True)
    return AgentService(ChatService(), agent_config_service, store_service, GitService(store_service))


def test_the_factory_builds_it_without_keys():
    assert isinstance(Factory.create_client(MOCK), MockClient)


def test_echo_with_estimated_tokens_and_no_cost(agents):
    record = agents.run("prova", "ciao mondo")

    assert record.ok and record.output == "[mock] ciao mondo"
    assert record.telemetry.agent_tokens.input_tokens > 0 and record.telemetry.agent_tokens.cost_eur == 0


def test_tool_on_command_then_its_result(agents):
    record = agents.run("prova", 'saluta /tool hello_world {"name": "Mario"}')

    assert record.ok and "hello_world" in record.output and "Mario" in record.output
    assert [call.name for call in record.telemetry.tool_calls] == ["hello_world"]


@pytest.mark.parametrize("task, error", [
    ("/tool git_status", "non disponibile (tool dell'agente: hello_world)"),
    ("/tool hello_world {nome: x}", "non validi (JSON)"),
])
def test_tool_errors_are_answers(agents, task, error):
    record = agents.run("prova", task)

    assert record.ok and error in record.output and record.telemetry.tool_calls == []
