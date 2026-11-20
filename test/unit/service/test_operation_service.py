"""«🤖 Automatico» of a development's Pre or Post: the commands,
then the automation, run by the worker without an agent; commands not
allowed are asked first; first error = stop; all fine = the Pre or Post is done."""
import shutil
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.container import Container
from core.error import ConflictError, NotFoundError, ValidationError
from domain.client.command.client import CommandClient, CommandResult
from models.domain.note import DevPhase, Phase, TaskStatus, TaskType
from models.domain.pipeline import PipelineRun, RunStatus
from models.domain.plan import OperationState, PlanChoice, StepKey, StepState
from service.command_service import CommandService
from service.operation_service import OperationService
from unit.service.test_copilot_service import project  # noqa: F401 (fixture: acme with api and web)
from unit.service.test_plan_service import activity, client, copilot, service  # noqa: F401 (fixtures)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


class FakeCommands(CommandClient):
    def __init__(self):
        self.calls: list[tuple[str, list[str]]] = []
        self.fail: str | None = None

    def run(self, cwd, arguments, timeout_seconds):
        self.calls.append((cwd.name, arguments))
        failed = self.fail is not None and " ".join(arguments).endswith(self.fail)
        return CommandResult(1 if failed else 0, "BUILD FAILURE" if failed else "ok")


class FakePipelines:
    def __init__(self):
        self.runs: dict[int, PipelineRun] = {}
        self.queued: list[tuple[int, str]] = []

    def list_pipelines(self, project_name):
        return [SimpleNamespace(id=4, name="Prova git")]

    def enqueue(self, pipeline_id, pipeline_input=""):
        run = PipelineRun(id=len(self.runs) + 1, pipeline_id=pipeline_id, input=pipeline_input)
        self.runs[run.id] = run
        self.queued.append((pipeline_id, pipeline_input))
        return run

    def get_run(self, run_id):
        if run_id not in self.runs:
            raise NotFoundError("run")
        return self.runs[run_id]


@pytest.fixture
def commands():
    return FakeCommands()


@pytest.fixture
def pipelines():
    return FakePipelines()


@pytest.fixture
def operations(stores, project_data_service, project_store, git_service, commands, pipelines, project):  # noqa: F811
    project_store.save(project_store.get("acme").model_copy(update={"allowed_commands": ["git pull", "mvn -B clean install"]}))
    return OperationService(stores.plans, project_data_service, CommandService(project_store, git_service, commands), pipelines)  # type: ignore[arg-type]


def _tasks(service, activity, *choices):  # noqa: F811
    plan = service.confirm("acme", activity, list(choices))
    return [item.task for item in plan.tasks]


def _run(stores, activity, task):  # noqa: F811
    return stores.plans.latest("acme", activity).operations[task]


def _dev(title, pre=None, post=None, **extra):
    return PlanChoice(title=title, type=TaskType.DEVELOPMENT, repository="api", pre=pre or DevPhase(), post=post or DevPhase(), **extra)


def _key(task, phase=Phase.PRE):
    return f"{task}|{phase.value}"


def test_commands_then_automation_and_the_pre_is_done(service, operations, activity, commands, pipelines, stores, project_data_service):  # noqa: F811
    [task] = _tasks(service, activity, _dev("Login", pre=DevPhase(commands=["git pull", " mvn  -B clean install ", " "], automation="Prova git")))
    assert project_data_service.agent_task("acme", task).pre.commands == ["git pull", "mvn -B clean install"]

    plan, pending = operations.start("acme", activity, task, Phase.PRE)
    assert pending == [] and plan.operations[_key(task)].state is OperationState.QUEUED
    assert _states(service, activity)[StepKey.PRE] is StepState.RUNNING
    with pytest.raises(ConflictError, match="sta già girando"):
        operations.start("acme", activity, task, Phase.PRE)
    with pytest.raises(ConflictError, match="aspetta che finisca"):
        service.skip("acme", activity, task, Phase.PRE)

    assert operations.run_next() is True
    assert [call[1][-1] for call in commands.calls] == ["pull", "install"] and commands.calls[0][0] == "api"
    run = _run(stores, activity, _key(task))
    assert run.state is OperationState.RUNNING and pipelines.queued == [(4, "api")] and "$ git pull" in run.output
    assert operations.run_next() is False  # the automation is still queued
    pipelines.runs[run.pipeline_run_id] = pipelines.runs[run.pipeline_run_id].model_copy(update={"status": RunStatus.DONE, "output": "nota salvata"})
    assert operations.run_next() is True
    run = _run(stores, activity, _key(task))
    assert run.state is OperationState.DONE and "nota salvata" in run.output
    assert project_data_service.agent_task("acme", task).status is TaskStatus.TODO  # the task goes on: delegation
    assert _states(service, activity)[StepKey.PRE] is StepState.DONE
    with pytest.raises(ConflictError, match="già chiuso"):
        operations.start("acme", activity, task, Phase.PRE)


def test_first_error_stops_then_again(service, operations, activity, commands, stores, project_data_service):  # noqa: F811
    [task] = _tasks(service, activity, _dev("Login", pre=DevPhase(commands=["mvn -B clean install", "git pull"])))
    commands.fail = "install"
    operations.start("acme", activity, task, Phase.PRE)
    operations.run_next()

    run = _run(stores, activity, _key(task))
    assert run.state is OperationState.FAILED and "uscito con 1" in run.error and "BUILD FAILURE" in run.output
    assert len(commands.calls) == 1
    path_step = service.path("acme", activity).tasks[0].steps[0]
    assert path_step.state is StepState.FAILED and "uscito con 1" in path_step.detail
    commands.fail = None
    operations.start("acme", activity, task, Phase.PRE)  # again after a failure
    operations.run_next()
    assert _run(stores, activity, _key(task)).state is OperationState.DONE


def test_the_post_runs_after_the_final_confirmation(service, operations, activity, stores, project_data_service):  # noqa: F811
    [task] = _tasks(service, activity, _dev("Login", post=DevPhase(commands=["git pull"])))
    with pytest.raises(ConflictError, match="dopo la conferma finale"):
        operations.start("acme", activity, task, Phase.POST)

    current = project_data_service.agent_task("acme", task)
    project_data_service.save_agent_task("acme", task, current.model_copy(update={"status": TaskStatus.DONE}))
    operations.start("acme", activity, task, Phase.POST)
    operations.run_next()
    assert _states(service, activity)[StepKey.POST] is StepState.DONE
    assert not service.path("acme", activity).tasks[0].current


def test_commands_not_allowed_are_asked_first(service, operations, activity, project_store, commands, stores):  # noqa: F811
    [task] = _tasks(service, activity, _dev("Branch", pre=DevPhase(commands=["git checkout -b feature/x"])))

    plan, pending = operations.start("acme", activity, task, Phase.PRE)
    assert pending == ["git checkout -b feature/x"] and _key(task) not in plan.operations
    assert [request.command for request in project_store.get("acme").command_requests] == ["git checkout -b feature/x"]
    operations.start("acme", activity, task, Phase.PRE)  # asked again: one request only
    assert len(project_store.get("acme").command_requests) == 1

    operations._commands.answer("acme", "git checkout -b feature/x", allow=True)  # «Solo stavolta»
    assert operations.start("acme", activity, task, Phase.PRE)[1] == []
    operations.run_next()
    assert _run(stores, activity, _key(task)).state is OperationState.DONE and commands.calls


def test_a_grant_used_meanwhile_and_a_failed_automation(service, operations, activity, project_store, pipelines, stores):  # noqa: F811
    first, second = _tasks(service, activity, _dev("Branch", pre=DevPhase(commands=["git checkout -b x"])),
                           _dev("Solo automation", pre=DevPhase(automation="Prova git")))
    project_store.save(project_store.get("acme").model_copy(update={"command_grants": ["git checkout -b x"]}))
    operations.start("acme", activity, first, Phase.PRE)
    project_store.save(project_store.get("acme").model_copy(update={"command_grants": []}))  # used by someone else
    operations.run_next()
    assert "non permesso" in _run(stores, activity, _key(first)).error

    operations.start("acme", activity, second, Phase.PRE)
    operations.run_next()
    run = _run(stores, activity, _key(second))
    pipelines.runs[run.pipeline_run_id] = pipelines.runs[run.pipeline_run_id].model_copy(update={"status": RunStatus.FAILED, "error": "step rotto"})
    operations.run_next()
    assert _run(stores, activity, _key(second)).error == "Automation fallita: step rotto"

    operations.start("acme", activity, second, Phase.PRE)
    operations.run_next()
    pipelines.runs.clear()
    operations.run_next()
    assert "non c'è più" in _run(stores, activity, _key(second)).error


def test_what_cannot_start(service, operations, activity, pipelines, project_data_service, stores):  # noqa: F811
    analysis, empty, wrong = _tasks(service, activity,
                                    PlanChoice(title="Analisi", type=TaskType.ANALYSIS),
                                    _dev("Vuoto"), _dev("Sbagliata", pre=DevPhase(automation="Altra")))
    with pytest.raises(ValidationError, match="solo nei task di sviluppo"):
        operations.start("acme", activity, analysis, Phase.PRE)
    with pytest.raises(ValidationError, match="fallo fare a Dev"):
        operations.start("acme", activity, empty, Phase.PRE)
    with pytest.raises(NotFoundError, match="Automation non trovata"):
        operations.start("acme", activity, wrong, Phase.PRE)
    with pytest.raises(NotFoundError, match="non è nel piano"):
        operations.start("acme", activity, "agent-task-altro.md", Phase.PRE)

    task = project_data_service.agent_task("acme", wrong)  # the automation renamed after the start: the worker fails it
    project_data_service.save_agent_task("acme", wrong, task.model_copy(update={"pre": DevPhase(automation="Prova git")}))
    operations.start("acme", activity, wrong, Phase.PRE)
    project_data_service.save_agent_task("acme", wrong, task)
    operations.run_next()
    assert "Automation non trovata" in _run(stores, activity, _key(wrong)).error

    project_data_service.save_agent_task("acme", wrong, task.model_copy(update={"pre": DevPhase(automation="Prova git")}))
    operations.start("acme", activity, wrong, Phase.PRE)
    project_data_service.delete_note("acme", wrong)
    operations.run_next()
    assert _run(stores, activity, _key(wrong)).error == "Il task non c'è più."
    assert operations.run_next() is False


def _states(service, activity):  # noqa: F811
    return {step.key: step.state for step in service.path("acme", activity).tasks[0].steps}


def test_the_api(stores, project_store, project, tmp_path):  # noqa: F811
    project_store.save(project_store.get("acme").model_copy(update={"allowed_commands": ["git status"]}))
    with TestClient(create_app(Container(stores=stores))) as http:
        ran = http.post("/projects/acme/commands/run", json={"repository": "api", "command": "git status"})
        assert ran.status_code == 200 and ran.json()["allowed"] is True and ran.json()["exit_code"] == 0
        asked = http.post("/projects/acme/commands/run", json={"repository": "api", "command": "rm -rf x"})
        assert asked.json() == {"allowed": False, "exit_code": None, "output": ""}
        assert http.post("/projects/acme/activities/attivita-x.md/plan/auto", json={"task": "agent-task-x.md", "phase": "pre"}).status_code == 404


def test_the_general_context_api(stores, project_store, project, config):  # noqa: F811
    (config.definitions_root / "context").mkdir(exist_ok=True)
    (config.definitions_root / "context" / "giro.md").write_text("# Il giro\n\nSi avvia con Avvia.", encoding="utf-8", newline="\n")  # the same text on Windows
    with TestClient(create_app(Container(stores=stores))) as http:
        expected = {"name": "giro.md", "title": "Il giro", "content": "# Il giro\n\nSi avvia con Avvia.", "origin": "tuo"}
        assert http.get("/projects/acme/context-general").json() == [expected]
