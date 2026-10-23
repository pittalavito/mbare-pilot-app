"""Automations as graphs in PipelineService and the store: edges with
conditions saved and read back by step name, node positions, renames, the
chain default for automations saved without edges, invalid graphs rejected."""
import pytest

from core.error import ValidationError
from models.domain.pipeline import INPUT_NODE, EdgeConditionKind, PipelineEdge, PipelineStep, StepAgent, StepKind
from models.domain.project import Project, ProjectSource
from service.pipeline_service import PipelineService

MODEL = "openai/gpt-4o"


@pytest.fixture
def service(store_service, agent_config_service):
    store_service.save_project(Project(name="acme", source=ProjectSource.FOLDER, root_path="/code/acme"))
    return PipelineService(store_service, agent_config_service)


def _step(name, x=0.0, y=0.0):
    return PipelineStep(name=name, kind=StepKind.AGENT, agent=StepAgent(system_prompt="Fai.", model=MODEL),
                        position_x=x, position_y=y)


def _edges(*triples):
    return [PipelineEdge(source=s, target=t, condition=c, value=v) for s, t, c, v in triples]


BRANCHES = _edges(
    (INPUT_NODE, "Check", EdgeConditionKind.ALWAYS, ""),
    ("Check", "Pull", EdgeConditionKind.CONTAINS, "OK"),
    ("Check", "Avvisa", EdgeConditionKind.OTHERWISE, ""),
)


def test_branches_and_positions_are_saved_and_read_back(service):
    created = service.create_pipeline("acme", "Flusso", steps=[_step("Check", 10, 20), _step("Pull"), _step("Avvisa")],
                                      edges=BRANCHES)

    read = service.get_pipeline(created.id)
    assert [(e.source, e.target, e.condition, e.value) for e in read.edges] == [
        (e.source, e.target, e.condition, e.value) for e in BRANCHES
    ]
    assert (read.steps[0].position_x, read.steps[0].position_y) == (10, 20)


def test_without_edges_the_steps_are_a_chain(service):
    created = service.create_pipeline("acme", "Catena", steps=[_step("A"), _step("B")])

    assert [(e.source, e.target) for e in created.edges] == [(INPUT_NODE, "A"), ("A", "B")]


def test_update_renames_a_step_and_its_edges_follow(service):
    created = service.create_pipeline("acme", "Flusso", steps=[_step("Check"), _step("Pull"), _step("Avvisa")],
                                      edges=BRANCHES)
    steps = [step.model_copy(update={"name": "Verifica"}) if step.name == "Check" else step for step in created.steps]
    edges = [edge.model_copy(update={
        "source": "Verifica" if edge.source == "Check" else edge.source,
        "target": "Verifica" if edge.target == "Check" else edge.target,
    }) for edge in created.edges]

    updated = service.update_pipeline(created.id, name="Flusso", steps=steps, edges=edges)

    assert [step.id for step in updated.steps] == [step.id for step in created.steps]  # same steps, renamed
    assert {(e.source, e.target) for e in service.get_pipeline(created.id).edges} == {
        (INPUT_NODE, "Verifica"), ("Verifica", "Pull"), ("Verifica", "Avvisa"),
    }


def test_removing_a_step_needs_its_edges_gone_too(service):
    created = service.create_pipeline("acme", "Flusso", steps=[_step("Check"), _step("Pull"), _step("Avvisa")],
                                      edges=BRANCHES)

    with pytest.raises(ValidationError, match="Avvisa non esiste"):
        service.update_pipeline(created.id, name="Flusso", steps=created.steps[:2], edges=created.edges)
    updated = service.update_pipeline(created.id, name="Flusso", steps=created.steps[:2], edges=BRANCHES[:1] + _edges(
        ("Check", "Pull", EdgeConditionKind.ALWAYS, "")))
    assert [step.name for step in updated.steps] == ["Check", "Pull"] and len(updated.edges) == 2


def test_invalid_graph_is_not_saved(service):
    with pytest.raises(ValidationError, match="Pull non ha collegamenti in ingresso"):
        service.create_pipeline("acme", "Rotto", steps=[_step("Check"), _step("Pull")], edges=BRANCHES[:1])
    assert service.list_pipelines("acme") == []
