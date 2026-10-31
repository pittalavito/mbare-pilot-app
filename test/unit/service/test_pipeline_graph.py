"""Automations as graphs: PipelineService and the store (edges with
conditions saved and read back by step name, node positions, renames, the
chain default, invalid graphs rejected) and PipelineRunner walking the graph
(branches by condition, joins, skipped steps, ``{nodo:Name}``, failures)."""
import pytest

from core.error import ValidationError
from fakes import FakeAgent
from models.domain.pipeline import (
    INPUT_NODE,
    EdgeConditionKind,
    PipelineEdge,
    PipelineStep,
    RunStatus,
    StepAgent,
    StepKind,
)
from models.domain.project import Project, ProjectSource
from service import agent_service as agent_service_module
from service.chat_service import ChatService
from service.pipeline_runner import PipelineRunner

MODEL = "openai/gpt-4o"


@pytest.fixture
def service(store_service, pipeline_service):
    store_service.save_project(Project(name="acme", source=ProjectSource.FOLDER, root_path="/code/acme"))
    return pipeline_service


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


# ------------------------------------------------------------ execution
# Fake agents echo their input ("echo: <input>"); the steps in ``runner.failing`` raise.

@pytest.fixture
def runner(store_service, monkeypatch, make_agent_service, git_service, project_data_service):
    failing: set[str] = set()

    def create_agent(definition, client, tools):
        return FakeAgent(RuntimeError("boom") if definition.name.rsplit("/", 1)[-1] in failing else None)

    monkeypatch.setattr(agent_service_module.AgentFactory, "create_agent", staticmethod(create_agent))
    chat = ChatService()
    monkeypatch.setattr(chat, "get_client", lambda model: object())
    git = git_service
    agents = make_agent_service(chat, git_service=git)
    runner = PipelineRunner(store_service, agents, git, project_data_service)
    runner.failing = failing
    return runner


# input ─► Check ─(contains OK)─► Pull ─┐
#                 └(otherwise)─► Avvisa ┴─► Fine
GRAPH_STEPS = ["Check", "Pull", "Avvisa", "Fine"]
GRAPH_EDGES = BRANCHES + _edges(
    ("Pull", "Fine", EdgeConditionKind.ALWAYS, ""), ("Avvisa", "Fine", EdgeConditionKind.ALWAYS, ""),
)


def _run(service, runner, steps, edges, pipeline_input):
    pipeline = service.create_pipeline("acme", "Grafo", steps=steps, edges=edges)
    service.enqueue(pipeline.id, pipeline_input)
    run = runner.run_next()
    return run, {step.name: step for step in run.steps}


def test_the_condition_picks_the_branch(service, runner):
    run, steps = _run(service, runner, [_step(n) for n in GRAPH_STEPS], GRAPH_EDGES, "tutto OK")

    assert run.status is RunStatus.DONE
    assert {name: step.status for name, step in steps.items()} == {
        "Check": RunStatus.DONE, "Pull": RunStatus.DONE, "Avvisa": RunStatus.SKIPPED, "Fine": RunStatus.DONE,
    }
    assert steps["Fine"].input == "echo: echo: tutto OK"  # only Pull's output arrived
    assert run.output == "echo: echo: echo: tutto OK"


def test_otherwise_when_no_text_condition_holds(service, runner):
    run, steps = _run(service, runner, [_step(n) for n in GRAPH_STEPS], GRAPH_EDGES, "qualcosa è andato storto")

    assert (steps["Pull"].status, steps["Avvisa"].status, steps["Fine"].status) == (
        RunStatus.SKIPPED, RunStatus.DONE, RunStatus.DONE,
    )


def test_a_step_with_more_inputs_gets_them_all_by_name(service, runner):
    edges = _edges(
        (INPUT_NODE, "Jira", EdgeConditionKind.ALWAYS, ""), (INPUT_NODE, "Git", EdgeConditionKind.ALWAYS, ""),
        ("Jira", "Riassumi", EdgeConditionKind.ALWAYS, ""), ("Git", "Riassumi", EdgeConditionKind.ALWAYS, ""),
    )

    run, steps = _run(service, runner, [_step("Jira"), _step("Git"), _step("Riassumi")], edges, "x")

    assert steps["Riassumi"].input == "## Jira\necho: x\n\n## Git\necho: x"
    assert run.output == "echo: ## Jira\necho: x\n\n## Git\necho: x"


def test_nothing_arrives_so_the_rest_is_skipped(service, runner):
    edges = BRANCHES[:2] + _edges(("Pull", "Fine", EdgeConditionKind.ALWAYS, ""))

    run, steps = _run(service, runner, [_step("Check"), _step("Pull"), _step("Fine")], edges, "KO")

    assert run.status is RunStatus.DONE
    assert (steps["Pull"].status, steps["Fine"].status) == (RunStatus.SKIPPED, RunStatus.SKIPPED)
    assert run.output == "echo: KO"  # the end of the path that ran


def test_node_placeholder_gets_that_steps_output(service, runner):
    steps = [_step("Check"), _step("Pull"), _step("Avvisa"),
             _step("Fine").model_copy(update={"input_template": "check={nodo:Check} avvisa={nodo:Avvisa}"})]

    _, by_name = _run(service, runner, steps, GRAPH_EDGES, "OK")

    assert by_name["Fine"].input == "check=echo: OK avvisa="  # Avvisa was skipped


def test_a_failing_branch_fails_the_run(service, runner):
    runner.failing.add("Pull")

    run, steps = _run(service, runner, [_step(n) for n in GRAPH_STEPS], GRAPH_EDGES, "OK")

    assert run.status is RunStatus.FAILED and "Pull" in run.error
    assert steps["Pull"].status is RunStatus.FAILED and "Fine" not in steps
