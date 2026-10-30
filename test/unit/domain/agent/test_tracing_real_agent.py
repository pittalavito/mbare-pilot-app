"""The tracing Adapter against a REAL datapizza Agent run (scripted client, no
network): guards against changes in the span shape datapizza emits."""
from datapizza.agents import Agent
from datapizza.clients import MockClient
from datapizza.core.clients import ClientResponse
from datapizza.core.clients.models import TokenUsage
from datapizza.tools import tool
from datapizza.tracing import ContextTracing
from datapizza.type import FunctionCallBlock, FunctionCallResultBlock, TextBlock

from domain.agent.tracing import Adapter
from models.domain.chat import ChatModel


class ScriptedClient(MockClient):
    """Calls the first tool on the first turn, then answers with its result."""

    def __init__(self, model_name: str, usage: TokenUsage):
        super().__init__(model_name=model_name)
        self._usage = usage

    def _invoke(self, input, tools=None, memory=None, **kwargs):
        if memory and isinstance(memory[-1].blocks[-1], FunctionCallResultBlock):
            return ClientResponse(content=[TextBlock(content=memory[-1].blocks[-1].result)], usage=self._usage)
        if tools:
            call = FunctionCallBlock(id="1", arguments={"name": "Mario"}, name=tools[0].name, tool=tools[0])
            return ClientResponse(content=[call], usage=self._usage)
        return ClientResponse(content=[TextBlock(content="Hello, Mario!")], usage=self._usage)


def test_real_agent_run_splits_agent_and_tool_tokens():
    inner_client = ScriptedClient("gpt-4o", TokenUsage(prompt_tokens=7, completion_tokens=3))

    @tool
    def llm_greeting(name: str) -> str:
        """Greets ``name`` using an LLM."""
        return inner_client.invoke(f"Saluta {name}").text

    agent = Agent(
        name="TestAgent",
        client=ScriptedClient("gpt-4o", TokenUsage(prompt_tokens=100, completion_tokens=20)),
        tools=[llm_greeting],
        max_steps=4,
    )

    with ContextTracing().trace("test") as current:
        step = agent.run("ciao")
        prices = {"gpt-4o": ChatModel(provider="openai", model="gpt-4o", input_per_1m=3.5, output_per_1m=10.0)}
        telemetry = Adapter.to_run_telemetry(current.get_spans(), prices)

    assert step.text == "Hello, Mario!"
    # two agent turns (tool call + final answer), one LLM call inside the tool
    assert (telemetry.agent_tokens.input_tokens, telemetry.agent_tokens.output_tokens) == (200, 40)
    assert (telemetry.tool_tokens.input_tokens, telemetry.tool_tokens.output_tokens) == (7, 3)
    assert telemetry.agent_tokens.cost_eur > 0

    [call] = telemetry.tool_calls
    assert call.name == "llm_greeting"
    assert "Mario" in call.arguments
    assert call.result == "Hello, Mario!"
    assert call.tokens.input_tokens == 7
    assert sorted(g.tool_name or "" for g in telemetry.generations) == ["", "", "llm_greeting"]
