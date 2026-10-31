from datetime import timedelta

import pytest

from domain.pipeline.graph import linear_edges
from domain.store.db.repository import transaction
from fakes import make_run_record
from models.domain.pipeline import INPUT_NODE, Pipeline, PipelineStep, StepAgent, StepKind


def test_save_run_writes_facts_tool_calls_and_trace(store_service):
    store_service.save_run(make_run_record("run-1"))

    [summary] = store_service.list_runs()
    assert summary.run_id == "run-1"
    assert summary.agent_tokens.input_tokens == 100
    assert summary.tool_tokens.input_tokens == 50
    assert summary.total_tokens.cost_eur == pytest.approx(0.000825)

    [tool_call] = store_service.list_tool_calls()
    assert tool_call.run_id == "run-1" and tool_call.tool_name == "hello_world"

    trace = store_service.get_run_trace("run-1")
    assert trace is not None and len(trace.generations) == 2


def test_saving_same_run_twice_replaces_tool_calls(store_service):
    store_service.save_run(make_run_record("run-1"))
    store_service.save_run(make_run_record("run-1"))

    assert len(store_service.list_runs()) == 1
    assert len(store_service.list_tool_calls()) == 1


def test_listed_timestamps_are_timezone_aware_utc(store_service):
    store_service.save_run(make_run_record("run-1"))

    [summary] = store_service.list_runs()
    [tool_call] = store_service.list_tool_calls()
    assert summary.created_at.utcoffset() == timedelta(0)
    assert tool_call.created_at.utcoffset() == timedelta(0)


# ------------------------------------------------------------- transactions

def _pipeline(*names: str, name: str = "P", pipeline_id: int | None = None) -> Pipeline:
    steps = [
        PipelineStep(name=step, kind=StepKind.AGENT, agent=StepAgent(system_prompt="Riassumi.", model="openai/gpt-4o"))
        for step in names
    ]
    return Pipeline(id=pipeline_id, project_name="acme", name=name, steps=steps, edges=linear_edges(steps))


def test_save_pipeline_is_all_or_nothing(store_service, monkeypatch):
    saved = store_service.save_pipeline(_pipeline("A", "B"))

    def broken_replace(pipeline_id, rows):
        raise RuntimeError("edges not written")

    monkeypatch.setattr(store_service._pipeline_edge_repository, "replace", broken_replace)
    with pytest.raises(RuntimeError):
        store_service.save_pipeline(_pipeline("C", name="Q", pipeline_id=saved.id))

    reloaded = store_service.get_pipeline(saved.id)
    assert reloaded.name == "P"
    assert [step.name for step in reloaded.steps] == ["A", "B"]
    assert [(edge.source, edge.target) for edge in reloaded.edges] == [(INPUT_NODE, "A"), ("A", "B")]


def test_rows_saved_in_a_transaction_stay_readable(store_service):
    saved = store_service.save_pipeline(_pipeline("A"))

    assert saved.id is not None and saved.steps[0].id is not None
    assert saved.steps[0].agent.model == "openai/gpt-4o"


def test_nested_transaction_joins_the_outer_one(store_service, engine):
    with pytest.raises(RuntimeError), transaction(engine):
        store_service.save_pipeline(_pipeline("A"))
        raise RuntimeError("outer block fails")

    assert store_service.list_pipelines("acme") == []
