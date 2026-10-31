from contextlib import contextmanager

import pytest
from sqlalchemy import event

from domain.pipeline.graph import linear_edges
from domain.store.db.repository import transaction
from models.domain.pipeline import INPUT_NODE, Pipeline, PipelineRun, PipelineStep, PipelineStepRun, StepAgent, StepKind

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


# ------------------------------------------------------------- query counts

@pytest.fixture
def count_queries(engine):
    """Counts the SQL statements run inside ``with count_queries() as counted:``."""
    @contextmanager
    def counting():
        counted = []

        def listener(connection, cursor, statement, *args):
            counted.append(statement)

        event.listen(engine, "before_cursor_execute", listener)
        try:
            yield counted
        finally:
            event.remove(engine, "before_cursor_execute", listener)
    return counting


def test_list_pipelines_loads_steps_and_edges_in_one_query_each(store_service, count_queries):
    for name in ("P", "Q", "R"):
        store_service.save_pipeline(_pipeline("A", "B", name=name))

    with count_queries() as counted:
        pipelines = store_service.list_pipelines("acme")

    assert [[step.name for step in pipeline.steps] for pipeline in pipelines] == [["A", "B"]] * 3
    assert all(len(pipeline.edges) == 2 for pipeline in pipelines)
    assert len(counted) == 3  # pipelines, steps, edges


def test_list_pipeline_runs_loads_step_runs_in_one_query(store_service, count_queries):
    pipeline = store_service.save_pipeline(_pipeline("A"))
    for _ in range(3):
        run = store_service.save_pipeline_run(PipelineRun(pipeline_id=pipeline.id, input="x"))
        store_service.save_pipeline_step_run(PipelineStepRun(pipeline_run_id=run.id, position=0, name="A", kind=StepKind.AGENT))
    store_service.save_pipeline_run(PipelineRun(pipeline_id=pipeline.id, input="no steps yet"))

    with count_queries() as counted:
        runs = store_service.list_pipeline_runs(pipeline.id)

    assert [len(run.steps) for run in runs] == [0, 1, 1, 1]
    assert len(counted) == 2  # runs, step runs


def test_listing_nothing_runs_no_child_query(store_service, count_queries):
    with count_queries() as counted:
        assert store_service.list_pipelines("empty") == []
    assert len(counted) == 1
