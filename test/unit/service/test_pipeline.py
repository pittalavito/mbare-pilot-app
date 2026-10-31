"""PipelineService (definitions, validation, queue) and PipelineRunner
(execution) on the in-memory store, with fake agents that echo their input."""
import importlib.util
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError as PydanticValidationError

from core.error import ConflictError, NotFoundError, ValidationError
from fakes import FakeAgent
from models.domain import pipeline as pipeline_module
from models.domain.agent import AgentConfig, AgentRole
from models.domain.pipeline import PipelineStep, RunStatus, StepAgent, StepKind
from models.domain.project import Project, ProjectSource
from models.domain.worker import WorkerStatus
from service import agent_service as agent_service_module
from service.agent_service import AgentService
from service.chat_service import ChatService
from service.git_service import GitService
from service.pipeline_runner import PipelineRunner
from service.pipeline_service import PipelineService
from service.project_data_service import ProjectDataService

MODEL = "openai/gpt-4o"


class _Agents(list):
    """Definitions of the agents built in a test; ``fail_on`` makes the agent
    with that name raise."""
    fail_on: str | None = None


@pytest.fixture
def agents(monkeypatch):
    built = _Agents()

    def create_agent(definition, client, tools):
        built.append(definition)
        return FakeAgent(RuntimeError("boom") if definition.name == built.fail_on else None)

    monkeypatch.setattr(agent_service_module.AgentFactory, "create_agent", staticmethod(create_agent))
    return built


@pytest.fixture
def agent_service(store_service, agent_config_service, monkeypatch):
    chat = ChatService()
    monkeypatch.setattr(chat, "get_client", lambda model: object())
    return AgentService(chat, agent_config_service, store_service, GitService(store_service))


@pytest.fixture
def service(store_service, agent_config_service, agents):
    for name in ("acme", "other"):
        store_service.save_project(Project(name=name, source=ProjectSource.FOLDER, root_path=f"/code/{name}"))
    return PipelineService(store_service, agent_config_service)


@pytest.fixture
def runner(store_service, agent_service):
    return PipelineRunner(store_service, agent_service, GitService(store_service), ProjectDataService(store_service))


def _own(name="Riassumi", prompt="Riassumi.", template="{input}", **agent) -> PipelineStep:
    return PipelineStep(
        name=name, kind=StepKind.AGENT, input_template=template,
        agent=StepAgent(system_prompt=prompt, model=MODEL, **agent),
    )


def _library(name="Saluta", agent="hello", template="{input}") -> PipelineStep:
    return PipelineStep(name=name, kind=StepKind.AGENT_CONFIG, agent_config_name=agent, input_template=template)


def _project_agent(agent_config_service, project_name, name):
    agent_config_service.save_role(AgentRole(name=f"{name}-role", project_name=project_name), create=True)
    prompt = agent_config_service.create_prompt_version(f"{name}-role", "Sei utile.")
    agent_config_service.save_config(AgentConfig(
        name=name, project_name=project_name, role_name=f"{name}-role", prompt_id=prompt.id, model=MODEL,
    ), create=True)


# ------------------------------------------------------------- definitions

def test_create_pipeline_with_ordered_steps(service):
    pipeline = service.create_pipeline("acme", " Report ", description=" settimanale ",
                                       steps=[_own(tool_names=["git_status"]), _library()])

    assert (pipeline.name, pipeline.description, pipeline.active) == ("Report", "settimanale", True)
    assert [(step.name, step.kind) for step in pipeline.steps] == [("Riassumi", StepKind.AGENT), ("Saluta", StepKind.AGENT_CONFIG)]
    assert all(step.id is not None for step in pipeline.steps)
    assert pipeline.steps[0].agent.tool_names == ["git_status"]
    assert [p.name for p in service.list_pipelines("acme")] == ["Report"]
    assert service.list_pipelines("other") == []


def test_steps_of_a_reloaded_class_are_accepted(service):
    """After a Streamlit hot reload the UI builds steps with a fresh copy of
    the PipelineStep class: same fields, different class object."""
    spec = importlib.util.spec_from_file_location("reloaded_pipeline", pipeline_module.__file__)
    reloaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reloaded)
    step = reloaded.PipelineStep.model_validate(_own("A").model_dump())
    assert not isinstance(step, PipelineStep)

    for created in (service.create_pipeline("acme", "P", steps=[step]),
                    service.update_pipeline(service.list_pipelines("acme")[0].id, name="P", steps=[step])):
        assert type(created.steps[0]) is PipelineStep and created.steps[0].name == "A"


def test_update_reorders_adds_and_removes_steps(service):
    pipeline = service.create_pipeline("acme", "P", steps=[_own("A"), _own("B"), _own("C")])
    a, b, c = pipeline.steps

    updated = service.update_pipeline(pipeline.id, name="P", steps=[c, a, _library("Nuovo")])

    assert [step.name for step in updated.steps] == ["C", "A", "Nuovo"]
    assert [updated.steps[0].id, updated.steps[1].id] == [c.id, a.id]
    assert b.id not in {step.id for step in updated.steps}


def test_prompt_version_grows_only_when_the_prompt_changes(service):
    pipeline = service.create_pipeline("acme", "P", steps=[_own("A", prompt="v1")])
    [step] = pipeline.steps

    same = service.update_pipeline(pipeline.id, name="P", steps=[step.model_copy(update={"name": "A2"})])
    changed_step = same.steps[0].model_copy(update={"agent": same.steps[0].agent.model_copy(update={"system_prompt": "v2"})})
    changed = service.update_pipeline(pipeline.id, name="P", steps=[changed_step])

    assert same.steps[0].agent.prompt_version == 1
    assert changed.steps[0].agent.prompt_version == 2


def test_unknown_step_ids_become_new_steps(service):
    pipeline = service.create_pipeline("acme", "P", steps=[_own("A")])
    foreign = _own("X").model_copy(update={"id": 9999})

    updated = service.update_pipeline(pipeline.id, name="P", steps=[foreign])

    assert updated.steps[0].id != 9999


@pytest.mark.parametrize("step, message", [
    (PipelineStep(name="A", kind=StepKind.AGENT), "configura il suo agente"),
    (_own(tool_names=["missing"]), "tool non disponibili"),
    (PipelineStep(name="L", kind=StepKind.AGENT_CONFIG), "scegli l'agente"),
    (_library(agent="missing"), "non esiste più"),
    (PipelineStep(name="F", kind=StepKind.FUNCTION, function_name="x"), "funzione"),
])
def test_invalid_steps_rejected(service, step, message):
    with pytest.raises(ValidationError, match=message):
        service.create_pipeline("acme", "P", steps=[step])


def test_library_agent_of_another_project_rejected(service, agent_config_service):
    _project_agent(agent_config_service, "other", "other-bot")
    _project_agent(agent_config_service, "acme", "acme-bot")

    service.create_pipeline("acme", "Ok", steps=[_library(agent="acme-bot")])
    with pytest.raises(ValidationError, match="appartiene al progetto other"):
        service.create_pipeline("acme", "P", steps=[_library(agent="other-bot")])
    assert {agent.name for agent in service.usable_agents("acme")} == {"hello", "acme-bot"}


def test_names_unique_per_project_and_required(service):
    service.create_pipeline("acme", "P")
    service.create_pipeline("other", "P")

    with pytest.raises(ConflictError):
        service.create_pipeline("acme", "p")
    with pytest.raises(PydanticValidationError):
        service.create_pipeline("acme", " ")
    with pytest.raises(NotFoundError):
        service.create_pipeline("nope", "P")


# -------------------------------------------------------------------- queue

def test_enqueue_requires_an_active_pipeline_with_steps(service):
    empty = service.create_pipeline("acme", "Vuota")
    off = service.create_pipeline("acme", "Spenta", active=False, steps=[_own()])

    with pytest.raises(ValidationError, match="non ha step"):
        service.enqueue(empty.id, "x")
    with pytest.raises(ValidationError, match="disattivata"):
        service.enqueue(off.id, "x")


def test_enqueue_queues_a_run(service):
    pipeline = service.create_pipeline("acme", "P", steps=[_own()])

    run = service.enqueue(pipeline.id, "ciao")

    assert (run.status, run.input, run.pipeline_id) == (RunStatus.QUEUED, "ciao", pipeline.id)
    assert [r.id for r in service.list_runs(pipeline.id)] == [run.id]


def test_workers_come_and_go_with_their_heartbeat(service, redis_client):
    now = datetime.now(timezone.utc)
    beat = WorkerStatus(worker_id="pc-1", host="pc", pid=1, started_at=now, last_seen=now)
    assert service.workers() == []

    service.heartbeat(beat)
    service.heartbeat(beat.model_copy(update={"busy_run_id": 7}))

    [worker] = service.workers()
    assert (worker.worker_id, worker.busy_run_id) == ("pc-1", 7)
    assert 0 < redis_client.ttl("app:worker:pc-1") <= 10  # gone by itself if the worker dies
    service.worker_stopped("pc-1")
    assert service.workers() == []


# ---------------------------------------------------------------- execution

def test_run_chains_the_steps(service, runner, agents, store_service):
    pipeline = service.create_pipeline("acme", "Report", steps=[
        _own("A", template="Commit: {input}", max_steps=6),
        _library("B", template="{input} | originale: {pipeline_input}"),
    ])
    queued = service.enqueue(pipeline.id, "ciao")
    claimed = []

    run = runner.run_next(on_claim=claimed.append)

    assert run.id == queued.id and run.status is RunStatus.DONE and run.error is None
    assert [r.id for r in claimed] == [queued.id]  # told before executing (worker heartbeat)
    first, second = run.steps
    assert (first.input, first.output) == ("Commit: ciao", "echo: Commit: ciao")
    assert second.input == "echo: Commit: ciao | originale: ciao"
    assert run.output == second.output == "echo: echo: Commit: ciao | originale: ciao"
    assert [definition.name for definition in agents] == ["pipeline/Report/A", "hello"]
    assert agents[0].max_steps == 6
    runs = {summary.run_id: summary for summary in store_service.list_runs()}
    assert {runs[step.agent_run_id].origin for step in run.steps} == {"pipeline"}
    assert {runs[step.agent_run_id].project_name for step in run.steps} == {"acme"}
    assert runner.run_next() is None


def test_failing_step_stops_the_run(service, runner, agents):
    pipeline = service.create_pipeline("acme", "P", steps=[_own("A"), _own("B"), _own("C")])
    agents.fail_on = "pipeline/P/B"
    service.enqueue(pipeline.id, "x")

    run = runner.run_next()

    assert run.status is RunStatus.FAILED and run.error.startswith("Step 2 (B):") and "boom" in run.error
    assert [(step.name, step.status) for step in run.steps] == [("A", RunStatus.DONE), ("B", RunStatus.FAILED)]
    assert run.steps[1].agent_run_id is not None


def test_step_that_cannot_start_fails_with_its_reason(service, runner, agent_config_service):
    pipeline = service.create_pipeline("acme", "P", steps=[_library()])
    service.enqueue(pipeline.id, "x")
    agent_config_service.set_role_active("hello", False)

    run = runner.run_next()

    assert run.status is RunStatus.FAILED and "disattivato" in run.error
    assert run.steps[0].agent_run_id is None


def test_runs_are_taken_oldest_first(service, runner):
    pipeline = service.create_pipeline("acme", "P", steps=[_own()])
    first = service.enqueue(pipeline.id, "1")
    second = service.enqueue(pipeline.id, "2")

    assert [runner.run_next().id, runner.run_next().id] == [first.id, second.id]


def test_history_survives_pipeline_edits(service, runner):
    pipeline = service.create_pipeline("acme", "P", steps=[_own("Vecchio")])
    service.enqueue(pipeline.id, "x")
    runner.run_next()

    service.update_pipeline(pipeline.id, name="P", steps=[_own("Nuovo")])

    [run] = service.list_runs(pipeline.id)
    assert run.steps[0].name == "Vecchio"


def test_delete_finished_or_queued_runs(service, runner):
    pipeline = service.create_pipeline("acme", "P", steps=[_own()])
    done = service.enqueue(pipeline.id, "1")
    runner.run_next()
    queued = service.enqueue(pipeline.id, "2")

    assert service.delete_run(done.id) is True
    assert service.delete_run(queued.id) is True
    assert service.list_runs(pipeline.id) == []
    with pytest.raises(NotFoundError):
        service.delete_run(done.id)


def test_running_run_cannot_be_deleted(service, store_service):
    pipeline = service.create_pipeline("acme", "P", steps=[_own()])
    service.enqueue(pipeline.id, "x")
    running = store_service.claim_next_pipeline_run()

    with pytest.raises(ValidationError, match="in corso"):
        service.delete_run(running.id)


def test_only_the_runs_of_dead_workers_fail(service, runner, store_service):
    pipeline = service.create_pipeline("acme", "P", steps=[_own()])
    for _ in range(3):
        service.enqueue(pipeline.id, "x")
    dead = store_service.claim_next_pipeline_run("pc-1")  # a worker took it, then died
    alive = store_service.claim_next_pipeline_run("pc-2")
    unknown = store_service.claim_next_pipeline_run()  # claimed before claimed_by
    assert alive.claimed_by == "pc-2"

    assert runner.fail_orphaned({"pc-2"}) == 2
    runs = {run.id: run for run in service.list_runs(pipeline.id)}
    assert runs[dead.id].status is RunStatus.FAILED and "interrotta" in runs[dead.id].error
    assert runs[unknown.id].status is RunStatus.FAILED
    assert runs[alive.id].status is RunStatus.RUNNING  # its worker still beats
    assert runner.fail_orphaned({"pc-2"}) == 0
