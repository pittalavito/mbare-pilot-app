"""Builders and fakes used across tests."""
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

from datapizza.tracing.tracing import agent_span, generation_span, tool_span
from pydantic import BaseModel

from models.domain.agent import AgentRunRecord, GenerationRecord, RunTelemetry, TokenSummary, ToolCallRecord


def as_dict(output) -> dict:
    """A tool's output as the JSON the model would read (tools return their
    output model when called directly; the agent layer serializes it)."""
    return json.loads(output.model_dump_json()) if isinstance(output, BaseModel) else json.loads(output)


def make_run_record(run_id: str = "run-1", created_at: datetime | None = None) -> AgentRunRecord:
    agent_tokens = TokenSummary(input_tokens=100, output_tokens=20, cost_eur=0.00055)
    tool_tokens = TokenSummary(input_tokens=50, output_tokens=10, cost_eur=0.000275)
    return AgentRunRecord(
        run_id=run_id,
        config_name="hello",
        role_name="hello",
        prompt_id=1,
        prompt_version=1,
        model="gpt-4o",
        latency_ms=12.5,
        created_at=created_at or datetime.now(timezone.utc),
        input="Saluta Mario",
        output="Hello, Mario!",
        telemetry=RunTelemetry(
            agent_tokens=agent_tokens,
            tool_tokens=tool_tokens,
            tool_calls=[ToolCallRecord(name="hello_world", arguments="{'name': 'Mario'}", latency_ms=1.0, tokens=tool_tokens)],
            generations=[
                GenerationRecord(model="gpt-4o", tokens=agent_tokens, latency_ms=5.0),
                GenerationRecord(model="gpt-4o", tokens=tool_tokens, latency_ms=2.0, tool_name="hello_world"),
            ],
        ),
    )


@contextmanager
def fake_generation(model: str, input_tokens: int, output_tokens: int):
    """Emit a datapizza ``generation`` span, like a real client call does."""
    with generation_span("client.invoke") as span:
        span.set_attribute("model_name", model)
        span.set_attribute("prompt_tokens_used", input_tokens)
        span.set_attribute("completion_tokens_used", output_tokens)
        span.set_attribute("cached_tokens_used", 0)
        span.set_attribute("thinking_tokens_used", 0)
        yield span


class FakeAgent:
    """Stands in for a datapizza Agent: emits the same span tree a real run
    does (agent -> generation, agent -> tool -> generation)."""

    def __init__(self, error: Exception | None = None):
        self._error = error
        self.memory = None
        """The memory of the last run, for assertions."""

    def run(self, task_input: str, memory=None):
        self.memory = memory
        with agent_span("Agent HelloAgent"):
            with fake_generation("gpt-4o", 100, 20):
                pass
            with tool_span("Tool hello_world") as span:
                span.set_attribute("tool_arguments", "{'name': 'Mario'}")
                with fake_generation("gpt-4o", 50, 10):
                    pass
                span.set_attribute("tool_result", '{"response": "Hello, Mario!"}')
            if self._error:
                raise self._error
        return SimpleNamespace(text=f"echo: {task_input}")


class FakeStructuredClient:
    """A chat client that answers ``structured_response`` with ``answer`` (or
    raises ``error``), emitting a generation span, and remembers what it got.
    ``tool_calls`` ((name, arguments) pairs) are asked first, one per call, when
    the call has tools (an agent with tools); ``tool_results`` gets what they gave."""

    def __init__(self, answer: BaseModel | None = None, error: Exception | None = None, tool_calls: list | None = None):
        self.answer = answer
        self.error = error
        self.calls: list[dict] = []
        self.tool_calls = list(tool_calls or [])
        self.tool_results: list[str] = []

    def structured_response(self, *, input, output_cls, system_prompt=None, tools=None, memory=None, **kwargs):
        from datapizza.core.clients.models import ClientResponse
        from datapizza.type import FunctionCallBlock, FunctionCallResultBlock, StructuredBlock
        self.calls.append({"input": input, "output_cls": output_cls, "system_prompt": system_prompt, "tools": [tool.name for tool in tools or []]})
        if memory is not None:
            self.tool_results += [block.result for turn in memory for block in turn.blocks if isinstance(block, FunctionCallResultBlock)]
        with fake_generation("gpt-4o", 300, 50):
            pass
        if self.error:
            raise self.error
        if tools and self.tool_calls:
            name, arguments = self.tool_calls.pop(0)
            tool = next(item for item in tools if item.name == name)
            return ClientResponse(content=[FunctionCallBlock(id=f"call-{len(self.calls)}", arguments=arguments, name=name, tool=tool)])
        answer = self.answer if self.answer is not None else output_cls(proposals=[])
        return ClientResponse(content=[StructuredBlock(content=answer)])


class ToolFailed(Exception):
    """A tool answered with its ToolErrorResponse (what fails an automation step)."""


def call_tool(name: str, context, **arguments):
    """The tool of the registry ``name``, built for ``context`` and called as a step would; ToolFailed with its error."""
    from tool.registry import TOOL_REGISTRY
    result = TOOL_REGISTRY[name].build(context)(**arguments)
    error = getattr(result, "error", None)
    if error:
        raise ToolFailed(error)
    return result
