"""The tests' settings (blocco 09) and, since plan 22, nothing automatic
around Copilot: a development finished by Copilot is «to verify» and nothing
else runs (cleaning and tests are a post development task, for Dev)."""
import shutil

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.container import Container
from models.domain.copilot import CopilotMessageRole, CopilotSessionStatus
from models.domain.dev import TestScope
from models.domain.note import AgentTask, TaskStatus
from unit.service.test_copilot_service import _service, _task, data, project  # noqa: F401 (fixtures)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def test_after_copilot_nothing_runs_by_itself(project, data, stores):  # noqa: F811
    service = _service(stores, data)
    note = _task(data)
    session = service.start("acme", note, "api")
    service.approve(session.id)
    session = service.run_next()

    assert session.status is CopilotSessionStatus.DONE and data.agent_task("acme", note).status is TaskStatus.TO_VERIFY
    assert not any("Verifica" in message.content for message in service.messages(session.id) if message.role is CopilotMessageRole.EVENT)
    assert not (project / "api" / "mbare-pilot").exists()  # plan 37: nothing in the repository


def test_the_task_scope_wins_over_the_project_default(project, data, pipeline_store):  # noqa: F811
    note = data.create_agent_task("acme", AgentTask(title="Login", tests=TestScope.TOUCHED))
    assert "Test: solo toccati" in data.read_note("acme", note)
    assert data.agent_task("acme", note).tests is TestScope.TOUCHED
    assert data.agent_task("acme", data.create_agent_task("acme", AgentTask(title="Altro"))).tests is None


def test_the_settings_api(stores, project):  # noqa: F811
    (project / "api" / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    with TestClient(create_app(Container(stores=stores))) as client:
        settings = client.get("/projects/acme/dev-settings").json()
        assert settings["test_scope"] == "all" and "prepare_automation" not in settings and "verify_automation" not in settings
        assert [(repo["repository"], repo["kind"], repo["detected_command"], repo["command"]) for repo in settings["repositories"]] == [
            ("api", "python", "pytest", ""), ("web", "unknown", "", "")]

        saved = client.put("/projects/acme/dev-settings", json={"test_scope": "touched", "commands": {"web": " make test ", "api": ""}}).json()

        assert saved["test_scope"] == "touched"
        assert [repo["command"] for repo in saved["repositories"]] == ["", "make test"]
