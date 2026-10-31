import pytest

from core.error import NotFoundError
from fakes import make_run_record
from service.run_service import RunService


def test_lists_the_runs_and_their_trace(run_store):
    run_store.save(make_run_record("run-1"))
    service = RunService(run_store)

    assert [summary.run_id for summary in service.list_runs()] == ["run-1"]
    assert [call.tool_name for call in service.list_tool_calls()] == ["hello_world"]
    assert service.trace("run-1").run_id == "run-1"


def test_a_missing_trace_is_not_found(run_store):
    with pytest.raises(NotFoundError, match="Trace non trovato: missing"):
        RunService(run_store).trace("missing")
