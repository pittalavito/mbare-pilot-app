"""Builders and fakes used across tests."""
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

from pydantic import BaseModel

from datapizza.tracing.tracing import agent_span, generation_span, tool_span

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
