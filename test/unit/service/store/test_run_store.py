from datetime import timedelta

import pytest

from fakes import make_run_record


def test_save_run_writes_facts_tool_calls_and_trace(run_store):
    run_store.save(make_run_record("run-1"))

    [summary] = run_store.list_runs()
    assert summary.run_id == "run-1"
    assert summary.agent_tokens.input_tokens == 100
    assert summary.tool_tokens.input_tokens == 50
    assert summary.total_tokens.cost_eur == pytest.approx(0.000825)

    [tool_call] = run_store.list_tool_calls()
    assert tool_call.run_id == "run-1" and tool_call.tool_name == "hello_world"

    trace = run_store.get_trace("run-1")
    assert trace is not None and len(trace.generations) == 2


def test_saving_same_run_twice_replaces_tool_calls(run_store):
    run_store.save(make_run_record("run-1"))
    run_store.save(make_run_record("run-1"))

    assert len(run_store.list_runs()) == 1
    assert len(run_store.list_tool_calls()) == 1


def test_listed_timestamps_are_timezone_aware_utc(run_store):
    run_store.save(make_run_record("run-1"))

    [summary] = run_store.list_runs()
    [tool_call] = run_store.list_tool_calls()
    assert summary.created_at.utcoffset() == timedelta(0)
    assert tool_call.created_at.utcoffset() == timedelta(0)
