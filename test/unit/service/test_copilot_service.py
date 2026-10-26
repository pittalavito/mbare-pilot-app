"""Agent tasks delegated to Copilot, end to end with a fake Copilot CLI
(test/fake_copilot.py) on real git repositories: planning chat, ok, execution
in the worker, the HEAD check, cancellation, the per-repository queue."""
import json
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from sqlmodel import SQLModel, create_engine

from core.error import ConflictError, UpstreamError, ValidationError
from domain.client.copilot.client import EXECUTION_DENIED, CopilotClient, CopilotMode
from models.domain.copilot import CopilotMessageRole, CopilotSessionStatus
from models.domain.note import AgentTask, TaskStatus
from models.domain.project import Project, ProjectSource
from service.copilot_service import CopilotService
from service.git_service import GitService
from service.project_data_service import ProjectDataService
from service.store_service import StoreService

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

FAKE = [sys.executable, str(Path(__file__).parents[2] / "fake_copilot.py")]


def _git(cwd, *args) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def project(store_service, tmp_path, monkeypatch):
    """Project ``acme`` with the repositories ``api`` and ``web`` (one commit each)."""
    monkeypatch.setenv("FAKE_COPILOT_STATE", str(tmp_path / "copilot-state"))
    root = tmp_path / "acme"
    for name in ("api", "web"):
        repo = root / name
        repo.mkdir(parents=True)
        _git(repo, "init", "-q")
        _git(repo, "config", "user.name", "Ada")
        _git(repo, "config", "user.email", "ada@example.com")
        (repo / "README.md").write_text(name, encoding="utf-8")
        _git(repo, "add", ".")
        _git(repo, "commit", "-qm", "init")
    store_service.save_project(Project(name="acme", source=ProjectSource.FOLDER, root_path=str(root)))
    return root


@pytest.fixture
def data(store_service):
    return ProjectDataService(store_service)


def _service(store_service, data, command=None, execution_timeout=30.0) -> CopilotService:
    return CopilotService(store_service, GitService(store_service), data, CopilotClient(command or FAKE),
                          planning_timeout_seconds=30, execution_timeout_seconds=execution_timeout)


def _task(data, title="Aggiungi copilot.txt") -> str:
    return data.create_agent_task("acme", AgentTask(title=title, objective="Un file di prova."))


def _turns(tmp_path, session) -> list[dict]:
    return json.loads((tmp_path / "copilot-state" / f"{session.copilot_session_id}.json").read_text(encoding="utf-8"))


def _roles(service, session) -> list[str]:
    return [message.role.value for message in service.messages(session.id)]


# ------------------------------------------------------------------ planning

def test_delegating_a_task_starts_the_planning_chat_on_the_same_copilot_session(store_service, data, project, tmp_path):
    service = _service(store_service, data)
    note = _task(data)

    session = service.start("acme", note, "api")
    session = service.send(session.id, "Sì, procedi pure così")

    assert session.status == CopilotSessionStatus.PLANNING and session.premium_requests == 2
    messages = service.messages(session.id)
    assert [m.role for m in messages] == [CopilotMessageRole.USER, CopilotMessageRole.COPILOT] * 2
    assert "# Aggiungi copilot.txt" in messages[0].content and "aspetta il mio ok" in messages[0].content
    assert messages[3].content.endswith("(turni in questa sessione: 2)")  # Copilot remembered the first turn
    turns = _turns(tmp_path, session)
    assert all(turn["mode"] == "plan" and "--allow-all-tools" not in turn["args"] for turn in turns)
    assert not (project / "api" / "copilot.txt").exists()


def test_a_session_needs_an_agent_task_a_repository_and_the_cli(store_service, data, project):
    service = _service(store_service, data)
    note = _task(data)
    data.save_note("acme", "appunti", "# libero")

    with pytest.raises(ValidationError):
        service.start("acme", "appunti.md", "api")  # not an agent task
    with pytest.raises(ValidationError):
        service.start("acme", note, "../fuori")
    with pytest.raises(ValidationError):
        service.start("acme", note, "")  # the project folder is not a repository
    with pytest.raises(UpstreamError):
        _service(store_service, data, command="definitely-not-copilot-xyz").start("acme", note, "api")


# ----------------------------------------------------------------- execution

def test_the_ok_runs_copilot_in_the_worker_without_commits_and_closes_the_task(store_service, data, project, tmp_path):
    service = _service(store_service, data)
    note = _task(data)
    session = service.start("acme", note, "api")
    (project / "api" / "mia-modifica.txt").write_text("mia", encoding="utf-8")

    session = service.approve(session.id)
    assert session.status == CopilotSessionStatus.QUEUED
    assert "già 1 file modificati" in service.messages(session.id)[-2].content  # the user's own change

    session = service.run_next()

    assert session.status == CopilotSessionStatus.DONE and not session.head_moved
    assert sorted(session.changed_files) == ["copilot.txt", "mia-modifica.txt"]
    assert (project / "api" / "copilot.txt").is_file()
    assert data.agent_task("acme", note).status == TaskStatus.DONE
    execution = _turns(tmp_path, session)[-1]
    assert execution["mode"] == "autopilot" and "--allow-all-tools" in execution["args"]
    assert all(tool in execution["args"] for tool in EXECUTION_DENIED)
    assert service.messages(session.id)[-2].content == "Ho creato copilot.txt. Criteri soddisfatti."
    assert service.run_next() is None  # nothing else queued


def test_a_commit_during_the_execution_is_reported_not_undone(store_service, data, project):
    service = _service(store_service, data)
    session = service.start("acme", _task(data, "Fai COMMIT"), "api")
    head = _git(project / "api", "rev-parse", "HEAD")

    service.approve(session.id)
    session = service.run_next()

    assert session.head_moved and session.head_before == head
    assert _git(project / "api", "log", "-1", "--format=%s") == "copilot"  # still there
    assert any("L'HEAD è cambiato" in message.content for message in service.messages(session.id))


def test_a_repository_without_commits_works_and_its_first_commit_is_reported(store_service, data, project):
    fresh = project / "nuovo"
    fresh.mkdir()
    _git(fresh, "init", "-q")  # no commit yet: no HEAD
    service = _service(store_service, data)

    clean = service.start("acme", _task(data, "Parti da zero"), "nuovo")
    service.approve(clean.id)
    clean = service.run_next()
    assert (clean.status, clean.head_before, clean.head_after, clean.head_moved) == (CopilotSessionStatus.DONE, "", "", False)
    assert clean.changed_files == ["copilot.txt"]

    committed = service.start("acme", _task(data, "Fai COMMIT subito"), "nuovo")
    service.approve(committed.id)
    committed = service.run_next()
    assert committed.head_before == "" and committed.head_moved
    assert any("nessun commit →" in message.content for message in service.messages(committed.id))


def test_a_failed_execution_reopens_the_task_and_the_chat_can_go_on(store_service, data, project):
    service = _service(store_service, data)
    note = _task(data, "FAIL apposta")
    session = service.start("acme", note, "api")
    service.approve(session.id)

    session = service.run_next()

    assert session.status == CopilotSessionStatus.FAILED and "errore simulato" in session.error
    assert data.agent_task("acme", note).status == TaskStatus.TODO
    assert service.send(session.id, "riproviamo").status == CopilotSessionStatus.PLANNING


def test_cancelling_stops_a_queued_or_running_execution(store_service, redis_client, project, tmp_path):
    """The worker and the API write the same session at the same time: on a
    SQLite file (a connection per thread, as Postgres) instead of the shared
    in-memory one."""
    engine = create_engine(f"sqlite:///{tmp_path / 'threads.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    store = StoreService(engine=engine, redis_client=redis_client)
    store.save_project(store_service.get_project("acme"))
    data = ProjectDataService(store)
    service = _service(store, data)
    queued = service.start("acme", _task(data, "Primo"), "api")
    service.approve(queued.id)
    assert service.cancel(queued.id).status == CopilotSessionStatus.CANCELLED

    running = service.start("acme", _task(data, "SLEEP lungo"), "api")
    service.approve(running.id)
    result = {}
    worker = threading.Thread(target=lambda: result.update(session=service.run_next()))
    worker.start()
    deadline = time.monotonic() + 15
    while service.session(running.id).status != CopilotSessionStatus.RUNNING:
        assert time.monotonic() < deadline, "never started"
        time.sleep(0.1)
    with pytest.raises(ConflictError):
        service.send(running.id, "ehi")
    service.cancel(running.id)
    worker.join(timeout=20)

    assert result["session"].status == CopilotSessionStatus.CANCELLED
    with pytest.raises(ConflictError):
        service.cancel(running.id)


def test_a_slow_execution_is_stopped_by_the_timeout(store_service, data, project):
    service = _service(store_service, data, execution_timeout=1)
    session = service.start("acme", _task(data, "SLEEP"), "api")
    service.approve(session.id)

    session = service.run_next()

    assert session.status == CopilotSessionStatus.FAILED and "Nessuna risposta" in session.error


def test_one_execution_at_a_time_per_repository(store_service, data, project):
    service = _service(store_service, data)
    first, second, other = (service.start("acme", _task(data, title), repo)
                            for title, repo in (("Uno", "api"), ("Due", "api"), ("Tre", "web")))
    for session in (first, second, other):
        service.approve(session.id)

    claimed = store_service.claim_next_copilot_session()  # first, now running on api
    assert claimed.id == first.id
    assert store_service.claim_next_copilot_session().id == other.id  # second waits: api is busy


def test_executions_left_running_by_a_dead_worker_fail_at_restart(store_service, data, project):
    service = _service(store_service, data)
    note = _task(data)
    session = service.start("acme", note, "api")
    service.approve(session.id)
    store_service.claim_next_copilot_session()

    assert service.fail_interrupted() == 1
    assert service.session(session.id).status == CopilotSessionStatus.FAILED
    with pytest.raises(ConflictError):
        service.approve(session.id)  # only from planning


# -------------------------------------------------------------------- client

def test_the_client_reports_a_missing_cli_and_reads_the_last_message(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_COPILOT_STATE", str(tmp_path / "state"))
    missing = CopilotClient("definitely-not-copilot-xyz")
    assert not missing.available and missing.version() is None
    assert "non trovato" in missing.turn(tmp_path, "s1", "ciao", CopilotMode.PLAN, 10).error

    turn = CopilotClient(FAKE).turn(tmp_path, "s2", "prima riga\nseconda riga", CopilotMode.PLAN, 30)

    assert (turn.error, turn.message, turn.premium_requests) == (None, "Domanda 1: confermi? (turni in questa sessione: 1)", 1)
    recorded = json.loads((tmp_path / "state" / "s2.json").read_text(encoding="utf-8"))
    assert recorded[0]["prompt"] == "prima riga\nseconda riga"  # multi-line prompts arrive whole
