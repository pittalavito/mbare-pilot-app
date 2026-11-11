"""Blocco 09: «Prepara sviluppo» at the delegation and «Verifica sviluppo»
after Copilot's execution, with the fake Copilot CLI on real repositories and
the two automations made of the real functions."""
import shutil
import sys

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.container import Container
from core.error import ConflictError
from domain.pipeline.graph import linear_edges
from models.domain.copilot import CopilotSessionStatus
from models.domain.dev import PREPARE_AUTOMATION, VERIFY_AUTOMATION, PrepareTarget, TestScope
from models.domain.note import AgentTask, TaskStatus
from models.domain.pipeline import Pipeline, PipelineStep, StepKind
from service.dev_checks_service import DevChecksService
from service.git_service import GitService
from service.pipeline_runner import PipelineRunner
from unit.service.test_copilot_service import _git, _service, _task, _task_dir, data, project  # noqa: F401 (fixtures)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _automation(pipeline_store, name, *functions, active=True):
    steps = [PipelineStep(name=function, kind=StepKind.FUNCTION, function_name=function, params=params) for function, params in functions]
    return pipeline_store.save_pipeline(Pipeline(project_name="acme", name=name, active=active, steps=steps, edges=linear_edges(steps)))


@pytest.fixture
def copilot(stores, data):  # noqa: F811
    git = GitService(stores.projects)
    checks = DevChecksService(stores.pipelines, PipelineRunner(stores.pipelines, None, git, data), git, data)  # type: ignore[arg-type]
    service = _service(stores, data)
    service.use_dev_checks(checks)
    return service, checks


def _branch(root, repository="api"):
    return _git(root / repository, "branch", "--show-current")


def test_the_delegation_prepares_the_repositories_first(project, data, copilot, pipeline_store, copilot_store):  # noqa: F811
    service, _ = copilot
    _automation(pipeline_store, PREPARE_AUTOMATION, ("git_check_clean", {}), ("git_checkout_branches", {}))
    note = _task(data)
    branch = _branch(project)

    session = service.start("acme", note, "api", prepare=[PrepareTarget(repository="api", branch=branch),
                                                         PrepareTarget(repository="web", branch="feature/login", base=_branch(project, "web"))])

    first = service.messages(session.id)[0].content
    assert first.startswith("🧰 Preparazione ok.") and "Pulito" in first and "- web: creato feature/login" in first
    assert _branch(project, "web") == "feature/login"

    (project / "api" / "README.md").write_text("changed", encoding="utf-8")
    with pytest.raises(ConflictError, match="Preparazione non riuscita, Copilot non è partito.") as error:
        service.start("acme", note, "api", prepare=[PrepareTarget(repository="api", branch=branch)])
    assert "Modifiche non committate" in str(error.value)
    assert len(copilot_store.list_sessions("acme")) == 1  # no session for the failed one


def test_without_the_automation_the_delegation_says_so_and_without_targets_nothing_runs(project, data, copilot, pipeline_store):  # noqa: F811
    service, checks = copilot
    note = _task(data)

    session = service.start("acme", note, "api", prepare=[PrepareTarget(repository="api", branch=_branch(project))])
    assert service.messages(session.id)[0].content.startswith("🧰 Il progetto non ha l'automation «Prepara sviluppo»")
    _automation(pipeline_store, PREPARE_AUTOMATION, ("git_check_clean", {}), active=False)
    assert not checks.has("acme", PREPARE_AUTOMATION)
    session = service.start("acme", note, "api")
    assert not service.messages(session.id)[0].content.startswith("🧰")


def test_a_development_to_verify_is_cleaned_and_tested(project, data, copilot, pipeline_store):  # noqa: F811
    service, _ = copilot
    _automation(pipeline_store, VERIFY_AUTOMATION, ("clean_mbare_pilot", {}), ("run_tests", {}))
    note = _task(data)
    session = service.start("acme", note, "api")
    assert _task_dir(project, note).is_dir()
    service.approve(session.id)

    session = service.run_next()

    assert session.status == CopilotSessionStatus.DONE and data.agent_task("acme", note).status == TaskStatus.TO_VERIFY
    last = service.messages(session.id)[-1].content
    assert last.startswith("🔍 Verifica ok.") and "cartella mbare-pilot/" in last and "non lo riconosco" in last
    assert not _task_dir(project, note).exists()


def test_failing_tests_are_reported_and_the_task_stays_to_verify(project, data, copilot, pipeline_store):  # noqa: F811
    service, _ = copilot
    _automation(pipeline_store, VERIFY_AUTOMATION, ("run_tests", {}))
    failing = f"{sys.executable} -c \"print('FAILED test_x - boom'); raise SystemExit(1)\""
    data.save_test_settings("acme", TestScope.ALL, {"api": failing})
    note = _task(data, tests=TestScope.ALL)
    service.approve(service.start("acme", note, "api").id)

    session = service.run_next()

    last = service.messages(session.id)[-1].content
    assert last.startswith("🔍 Verifica fallita.") and "Test falliti" in last and "FAILED test_x - boom" in last
    assert data.agent_task("acme", note).status == TaskStatus.TO_VERIFY  # the user decides


def test_a_verification_that_cannot_start_is_reported(project, data, copilot, pipeline_store):  # noqa: F811
    service, _ = copilot
    _automation(pipeline_store, VERIFY_AUTOMATION, ("run_tests", {}))
    note = _task(data)
    session = service.approve(service.start("acme", note, "api").id)
    data.delete_note("acme", note)  # the task is gone: its scope cannot be read

    session = service.run_next()

    assert service.messages(session.id)[-1].content.startswith("🔍 Verifica fallita.")


def test_the_task_scope_wins_over_the_project_default(project, data, pipeline_store):  # noqa: F811
    note = data.create_agent_task("acme", AgentTask(title="Login", tests=TestScope.TOUCHED))
    assert "Test: solo toccati" in data.read_note("acme", note)
    assert data.agent_task("acme", note).tests is TestScope.TOUCHED
    assert data.agent_task("acme", data.create_agent_task("acme", AgentTask(title="Altro"))).tests is None


def test_the_settings_api(stores, project):  # noqa: F811
    (project / "api" / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    with TestClient(create_app(Container(stores=stores))) as client:
        settings = client.get("/projects/acme/dev-settings").json()
        assert settings["test_scope"] == "all" and not settings["prepare_automation"] and not settings["verify_automation"]
        assert [(repo["repository"], repo["kind"], repo["detected_command"], repo["command"]) for repo in settings["repositories"]] == [
            ("api", "python", "pytest", ""), ("web", "unknown", "", "")]

        saved = client.put("/projects/acme/dev-settings", json={"test_scope": "touched", "commands": {"web": " make test ", "api": ""}}).json()

        assert saved["test_scope"] == "touched"
        assert [repo["command"] for repo in saved["repositories"]] == ["", "make test"]
