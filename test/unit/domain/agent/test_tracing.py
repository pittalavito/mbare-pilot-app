import pytest
from datapizza.tracing import ContextTracing
from datapizza.tracing.tracing import tool_span

from domain.agent.tracing import Adapter
from domain.chat.models_default import DEFAULT_CHAT_MODELS
from fakes import FakeAgent
from models.domain.agent import RunTelemetry


def _trace(run) -> RunTelemetry:
    with ContextTracing().trace("test") as current:
        try:
            run()
        except Exception:
            pass
        return Adapter.to_run_telemetry(current.get_spans(), {p.model: p for p in DEFAULT_CHAT_MODELS})


def test_tokens_split_between_agent_and_tool():
    telemetry = _trace(lambda: FakeAgent().run("ciao"))

    assert (telemetry.agent_tokens.input_tokens, telemetry.agent_tokens.output_tokens) == (100, 20)
    assert (telemetry.tool_tokens.input_tokens, telemetry.tool_tokens.output_tokens) == (50, 10)
    assert telemetry.total_tokens.input_tokens == 150
    assert telemetry.agent_tokens.cost_eur == pytest.approx(100 / 1e6 * 3.5 + 20 / 1e6 * 10.0)


def test_tool_call_has_its_own_tokens_args_and_result():
    telemetry = _trace(lambda: FakeAgent().run("ciao"))

    [call] = telemetry.tool_calls
    assert call.name == "hello_world"
    assert call.arguments == "{'name': 'Mario'}"
    assert call.result == '{"response": "Hello, Mario!"}'
    assert call.ok and call.tokens.input_tokens == 50
    assert [g.tool_name for g in telemetry.generations] == [None, "hello_world"]


def test_failed_tool_call_is_marked_not_ok():
    def run():
        with tool_span("Tool broken"):
            raise RuntimeError("boom")

    [call] = _trace(run).tool_calls
    assert call.name == "broken" and not call.ok and "boom" in call.error
