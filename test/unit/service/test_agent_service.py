import pytest

from core.error import NotFoundError
from fakes import FakeAgent
from service import agent_service as agent_service_module
from service.chat_service import ChatService


@pytest.fixture
def agent_service(monkeypatch, make_agent_service):
    chat_service = ChatService()
    monkeypatch.setattr(chat_service, "get_client", lambda model: object())
    return make_agent_service(chat_service)


def _use_fake_agent(monkeypatch, error: Exception | None = None):
    monkeypatch.setattr(
        agent_service_module.AgentFactory, "create_agent",
        staticmethod(lambda spec, client, tools: FakeAgent(error)),
    )


def test_run_persists_tokens_from_datapizza_spans(agent_service, monkeypatch, run_store):
    _use_fake_agent(monkeypatch)

    record = agent_service.run("hello", "ciao")

    assert record.ok and record.output == "echo: ciao"
    assert (record.config_name, record.role_name, record.prompt_version, record.model) == ("hello", "hello", 1, "gpt-4o")
    assert record.telemetry.agent_tokens.input_tokens == 100
    assert record.telemetry.tool_tokens.input_tokens == 50
    assert record.telemetry.agent_tokens.cost_eur == pytest.approx(100 / 1e6 * 3.5 + 20 / 1e6 * 10.0)

    [summary] = run_store.list_runs()
    assert summary.total_tokens.input_tokens == 150
    assert summary.tool_names == ["hello_world"]
    [tool_call] = run_store.list_tool_calls()
    assert tool_call.tool_name == "hello_world" and tool_call.tokens.input_tokens == 50
    assert run_store.get_trace(record.run_id).tool_calls[0].result is not None


def test_run_persists_failed_run_with_partial_tokens(agent_service, monkeypatch, run_store):
    _use_fake_agent(monkeypatch, error=RuntimeError("boom"))

    record = agent_service.run("hello", "ciao")

    assert not record.ok and record.error == "boom"
    assert record.telemetry.total_tokens.input_tokens == 150
    assert run_store.list_runs()[0].ok is False


def test_run_unknown_config_raises(agent_service):
    with pytest.raises(NotFoundError):
        agent_service.run("missing", "ciao")


def test_agent_is_built_from_config(agent_service, agent_config_service, monkeypatch):
    built = {}

    def capture(definition, client, tools):
        built.update(prompt=definition.system_prompt, tools=[t.name for t in tools], max_steps=definition.max_steps)
        return FakeAgent()

    monkeypatch.setattr(agent_service_module.AgentFactory, "create_agent", staticmethod(capture))
    agent_service.run("hello", "ciao")

    assert built == {
        "prompt": agent_config_service.latest_prompt("hello").text,
        "tools": ["hello_world"],
        "max_steps": 4,
    }


def test_tools_are_built_with_the_runs_project(agent_service, monkeypatch):
    seen = {}

    def fake_build_tools(names, context):
        seen["project"] = context.project_name
        return []

    monkeypatch.setattr(agent_service_module, "build_tools", fake_build_tools)
    _use_fake_agent(monkeypatch)

    agent_service.run("hello", "ciao", project_name="acme")

    assert seen == {"project": "acme"}
