"""The chatbot's Copilot tools with the fake Copilot CLI on a real repository:
list the agent tasks, delegate one (the planning chat opens, nothing changes),
read its status. Only in a chatbot's run of a project."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from domain.client.copilot.client import CopilotClient
from fakes import as_dict
from models.domain.agent import RunOrigin
from models.domain.note import AgentTask
from models.domain.project import Project, ProjectSource
from service.copilot_service import CopilotService
from tool.context import ToolContext
from tool.list.copilot.copilot_status import COPILOT_STATUS
from tool.list.copilot.delegate_task import DELEGATE_TASK
from tool.list.copilot.list_agent_tasks import LIST_AGENT_TASKS

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

FAKE = [sys.executable, str(Path(__file__).parents[2] / "fake_copilot.py")]


@pytest.fixture
def context(store_service, tmp_path, monkeypatch, git_service, project_data_service, project_store, copilot_store) -> ToolContext:
    """Chatbot run of project ``acme`` (repository ``api``) with the task «Fix porto»."""
    monkeypatch.setenv("FAKE_COPILOT_STATE", str(tmp_path / "state"))
    repo = tmp_path / "acme" / "api"
    repo.mkdir(parents=True)
    for args in (["init", "-q"], ["-c", "user.name=A", "-c", "user.email=a@b.it", "commit", "-q", "--allow-empty", "-m", "init"]):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path=str(tmp_path / "acme")))
    data = project_data_service
    data.create_agent_task("acme", AgentTask(title="Fix porto"))
    git = git_service
    copilot = CopilotService(store_service, copilot_store, git, data, CopilotClient(FAKE), planning_timeout_seconds=30, execution_timeout_seconds=30)
    return ToolContext(project_name="acme", git=git, origin=RunOrigin.CHAT, project_data=data, copilot=copilot)


def test_the_chatbot_lists_the_tasks_and_delegates_one(context):
    tasks = as_dict(LIST_AGENT_TASKS.build(context).func())
    assert tasks == {"tasks": [{"task": "agent-task-fix-porto.md", "title": "Fix porto", "status": "todo", "copilot_status": None}]}

    delegated = as_dict(DELEGATE_TASK.build(context).func(task="agent-task-fix-porto.md", repository="api"))

    assert delegated["copilot_answered"] and delegated["repository"] == "api"
    assert delegated["chat"] == f"/projects/acme/copilot?session={delegated['session_id']}"
    assert "Domanda" not in str(delegated)  # Copilot's answer stays in its chat
    assert as_dict(LIST_AGENT_TASKS.build(context).func())["tasks"][0]["copilot_status"] == "planning"
    status = as_dict(COPILOT_STATUS.build(context).func(session_id=delegated["session_id"]))
    assert (status["status"], status["changed_files"], status["head_moved"]) == ("planning", 0, False)


def test_errors_come_back_to_the_chatbot(context):
    delegate = DELEGATE_TASK.build(context).func

    assert "non è un agent task" in as_dict(delegate(task="appunti.md", repository="api"))["error"]
    missing_repo = as_dict(delegate(task="agent-task-fix-porto.md", repository="web"))
    assert "inesistente" in missing_repo["error"] and missing_repo["repositories"] == ["api"]
    assert "non trovata" in as_dict(COPILOT_STATUS.build(context).func(session_id=999))["error"]


def test_only_in_a_chatbot_run(context):
    manual = ToolContext(project_name="acme", git=context.git, origin=RunOrigin.MANUAL,
                         project_data=context.project_data, copilot=context.copilot)

    for spec, kwargs in ((LIST_AGENT_TASKS, {}), (DELEGATE_TASK, {"task": "agent-task-fix-porto.md", "repository": "api"}),
                         (COPILOT_STATUS, {"session_id": 1})):
        assert "solo nel chatbot" in as_dict(spec.build(manual).func(**kwargs))["error"]
