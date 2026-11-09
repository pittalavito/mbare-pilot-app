"""The Copilot API over the in-memory store, with the fake Copilot CLI."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.container import Container
from domain.client.copilot.client import CopilotClient
from models.domain.project import Project, ProjectSource

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

FAKE = [sys.executable, str(Path(__file__).parents[2] / "fake_copilot.py")]


@pytest.fixture
def client(stores, tmp_path, monkeypatch, project_store):
    monkeypatch.setenv("FAKE_COPILOT_STATE", str(tmp_path / "state"))
    repo = tmp_path / "acme"
    repo.mkdir()
    for args in (["init", "-q"], ["-c", "user.name=A", "-c", "user.email=a@b.it", "commit", "-q", "--allow-empty", "-m", "init"]):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path=str(repo)))
    container = Container(stores=stores)
    container.copilot_service._client = CopilotClient(FAKE)
    with TestClient(create_app(container)) as client:
        yield client


def test_delegate_chat_approve_cancel_and_delete(client):
    created = client.post("/projects/acme/agent-tasks", json={"title": "Prova"}).json()
    assert (created["status"], created["type"]) == ("created", "development")  # the defaults of a new task
    task = created["name"]

    session = client.post("/projects/acme/copilot-sessions", json={"task_note": task})
    assert session.status_code == 201
    session = session.json()
    assert session["status"] == "planning" and "copilot_session_id" not in session
    sid = session["id"]

    assert client.post(f"/copilot-sessions/{sid}/messages", json={"text": "ok così"}).json()["premium_requests"] == 2
    roles = [m["role"] for m in client.get(f"/copilot-sessions/{sid}/messages").json()]
    assert roles == ["event", "user", "copilot", "user", "copilot"]  # event: the task is not refined yet
    assert client.post(f"/copilot-sessions/{sid}/messages", json={"text": "  "}).status_code == 400

    usage = client.get(f"/copilot-sessions/{sid}/turns").json()
    assert [turn["phase"] for turn in usage["turns"]] == ["plan", "plan"]
    assert (usage["total"]["premium_requests"], usage["total"]["ai_credits"], usage["total"]["input_tokens"]) == (2, 0.2, 2000)
    assert [turn["session_id"] for turn in client.get("/observability/copilot/turns", params={"project": "acme"}).json()] == [sid, sid]
    assert client.get("/observability/copilot/models", params={"days": 7}).json() == [{
        "model": "fake-default", "turns": 2,
        "usage": {"premium_requests": 2, "ai_credits": 0.2, "input_tokens": 2000, "output_tokens": 20, "cache_read_tokens": 1000,
                  "cache_write_tokens": 200, "reasoning_tokens": 10, "api_duration_ms": 100},
    }]

    assert client.post(f"/copilot-sessions/{sid}/approve").json()["status"] == "queued"
    assert client.delete(f"/copilot-sessions/{sid}").status_code == 409  # queued: cancel it first
    assert client.post(f"/copilot-sessions/{sid}/cancel").json()["status"] == "cancelled"
    assert [s["id"] for s in client.get("/projects/acme/copilot-sessions").json()] == [sid]
    assert client.delete(f"/copilot-sessions/{sid}").status_code == 204
    assert client.get(f"/copilot-sessions/{sid}").status_code == 404


def test_status_and_validation(client):
    assert client.get("/copilot/status").json() == {  # the fake has no --version
        "installed": False, "version": None, "definition_error": None, "prompts": [], "type_prompts": {}, "models": [], "default_model": "",
    }
    assert client.get("/copilot/status", params={"project": "acme"}).json()["definition_error"] is None
    assert client.post("/projects/acme/copilot-sessions", json={"task_note": "agent-task-manca.md"}).status_code == 404


def test_the_status_says_which_prompt_each_task_type_uses(client, config):
    (config.definitions_root / "coding-agent").mkdir()
    (config.definitions_root / "coding-agent" / "analisi.md").write_text("Analizza.\n{task_folder}", encoding="utf-8")
    path = config.definitions_root / "global-coding-agent.yml"
    path.write_text(path.read_text(encoding="utf-8") + "type_prompts: {analysis: analisi}\n", encoding="utf-8")

    status = client.get("/copilot/status").json()

    assert (status["prompts"], status["type_prompts"]) == (["analisi"], {"analysis": "analisi"})


def test_deleting_the_sessions_of_a_task(client):
    task = client.post("/projects/acme/agent-tasks", json={"title": "Da buttare"}).json()["name"]
    client.post("/projects/acme/copilot-sessions", json={"task_note": task})

    assert client.delete("/projects/acme/copilot-sessions", params={"task_note": task}).json() == {"deleted": 1}
    assert client.get("/projects/acme/copilot-sessions").json() == []


def test_an_analysis_is_saved_as_a_note_and_a_task_to_verify_is_sent_back(client):
    task = client.post("/projects/acme/agent-tasks", json={"title": "Capire", "type": "analysis", "status": "todo"}).json()["name"]
    sid = client.post("/projects/acme/copilot-sessions", json={"task_note": task}).json()["id"]
    assert client.post(f"/copilot-sessions/{sid}/approve").status_code == 409  # an analysis is never executed

    saved = client.post(f"/copilot-sessions/{sid}/save-note").json()

    assert saved["note"] == "analisi-capire.md" and saved["session"]["id"] == sid
    assert next(item for item in client.get("/projects/acme/agent-tasks").json() if item["name"] == task)["status"] == "done"

    development = client.post("/projects/acme/agent-tasks", json={"title": "Sviluppa", "status": "todo"}).json()["name"]
    sid = client.post("/projects/acme/copilot-sessions", json={"task_note": development}).json()["id"]
    assert client.post(f"/copilot-sessions/{sid}/send-back", json={"text": "rifai"}).status_code == 409  # not to verify
    client.put(f"/projects/acme/agent-tasks/{development}", json={"title": "Sviluppa", "status": "to_verify"})

    sent = client.post(f"/copilot-sessions/{sid}/send-back", json={"text": "Aggiungi un test"}).json()

    assert sent["status"] == "queued"
