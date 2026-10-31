"""Agent tasks delegated to Copilot, end to end with a fake Copilot CLI
(test/fake_copilot.py) on real git repositories: planning chat (each turn
queued for the worker), ok, execution in the worker, the HEAD check, cancellation, the per-repository queue."""
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
from domain.client.copilot.client import CopilotClient, CopilotMode
from models.domain.copilot import CopilotMessageRole, CopilotPlanningTurn, CopilotSessionStatus
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


def _service(store_service, data, command=None, execution_timeout=30.0, planning_timeout=30.0) -> CopilotService:
    return CopilotService(store_service, GitService(store_service), data, CopilotClient(command or FAKE),
                          planning_timeout_seconds=planning_timeout, execution_timeout_seconds=execution_timeout)


def _threaded_store(store_service, redis_client, tmp_path) -> StoreService:
    """The worker and the API write the same session at the same time: on a
    SQLite file (a connection per thread, as Postgres) instead of the shared
    in-memory one."""
    engine = create_engine(f"sqlite:///{tmp_path / 'threads.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    store = StoreService(engine=engine, redis_client=redis_client)
    store.save_project(store_service.get_project("acme"))
    return store


def _wait(condition, what: str) -> None:
    deadline = time.monotonic() + 15
    while not condition():
        assert time.monotonic() < deadline, what
        time.sleep(0.1)


def _task(data, title="Aggiungi copilot.txt") -> str:
    return data.create_agent_task("acme", AgentTask(title=title, objective="Un file di prova."))


def _turns(tmp_path, session) -> list[dict]:
    return json.loads((tmp_path / "copilot-state" / f"{session.copilot_session_id}.json").read_text(encoding="utf-8"))


def _plan(service) -> None:
    """The worker's side of the planning chat: answers every queued turn."""
    while service.plan_next() is not None:
        pass


def _start(service, *args, **kwargs):
    """``start`` and the worker's answer to the first turn."""
    session = service.start(*args, **kwargs)
    _plan(service)
    return service.session(session.id)


def _send(service, session_id, text):
    """``send`` and the worker's answer."""
    service.send(session_id, text)
    _plan(service)
    return service.session(session_id)


def _roles(service, session) -> list[str]:
    return [message.role.value for message in service.messages(session.id)]


# ------------------------------------------------------------------ planning

def test_delegating_a_task_starts_the_planning_chat_on_the_same_copilot_session(store_service, data, project, tmp_path):
    service = _service(store_service, data)
    note = _task(data)

    session = _start(service, "acme", note, "api")
    session = _send(service, session.id, "Sì, procedi pure così")

    assert session.status == CopilotSessionStatus.PLANNING and session.premium_requests == 2
    messages = service.messages(session.id)
    assert [m.role for m in messages] == [CopilotMessageRole.USER, CopilotMessageRole.COPILOT] * 2
    assert "# Aggiungi copilot.txt" in messages[0].content and "aspetta il mio ok" in messages[0].content
    assert messages[3].content.endswith("(turni in questa sessione: 2)")  # Copilot remembered the first turn
    turns = _turns(tmp_path, session)
    assert all(turn["mode"] == "plan" and "--allow-all-tools" not in turn["args"] for turn in turns)
    assert not (project / "api" / "copilot.txt").exists()


def test_the_api_answers_at_once_and_the_worker_runs_the_planning_turn(store_service, data, project, tmp_path):
    service = _service(store_service, data)

    session = service.start("acme", _task(data), "api")

    assert (session.status, session.planning_turn) == (CopilotSessionStatus.PLANNING, CopilotPlanningTurn.QUEUED)
    assert _roles(service, session) == ["user"] and not (tmp_path / "copilot-state").exists()  # Copilot not started
    with pytest.raises(ConflictError, match="ancora rispondendo"):
        service.send(session.id, "ci sei?")  # one turn at a time
    with pytest.raises(ConflictError, match="ancora rispondendo"):
        service.approve(session.id)
    with pytest.raises(ConflictError):
        service.delete(session.id)

    answered = service.plan_next()

    assert answered.id == session.id and answered.planning_turn is None and answered.premium_requests == 1
    assert _roles(service, session) == ["user", "copilot"]
    assert _turns(tmp_path, session)[0]["prompt"] == service.messages(session.id)[0].content  # the saved message is the prompt
    assert service.plan_next() is None
    assert service.send(session.id, "procedi").planning_turn == CopilotPlanningTurn.QUEUED
    assert [turn.phase.value for turn in service.session_turns(session.id)] == ["plan"]  # the second one is not run yet


def test_a_planning_turn_runs_while_the_repository_has_an_execution(store_service, data, project):
    """Plan mode only reads: it does not wait for the repository's execution."""
    service = _service(store_service, data)
    executing = _start(service, "acme", _task(data, "Uno"), "api")
    service.approve(executing.id)
    assert store_service.claim_next_copilot_session().id == executing.id  # running on api
    chatting = service.start("acme", _task(data, "Due"), "api")

    assert service.plan_next().id == chatting.id
    assert _roles(service, chatting) == ["user", "copilot"]


def test_cancelling_a_queued_planning_turn_keeps_the_chat_open(store_service, data, project, tmp_path):
    service = _service(store_service, data)
    session = service.start("acme", _task(data), "api")

    session = service.cancel(session.id)

    assert (session.status, session.planning_turn) == (CopilotSessionStatus.PLANNING, None)
    assert service.plan_next() is None and not (tmp_path / "copilot-state").exists()
    assert _send(service, session.id, "riproviamo").premium_requests == 1  # Copilot answers the new message
    with pytest.raises(ConflictError):
        service.cancel(session.id)  # nothing pending


def test_cancelling_a_running_planning_turn_stops_copilot(store_service, redis_client, project, tmp_path):
    store = _threaded_store(store_service, redis_client, tmp_path)
    data = ProjectDataService(store)
    service = _service(store, data)
    session = _start(service, "acme", _task(data), "api")
    service.send(session.id, "PENSACI bene")
    result = {}
    worker = threading.Thread(target=lambda: result.update(session=service.plan_next()))
    worker.start()
    _wait(lambda: service.session(session.id).planning_turn == CopilotPlanningTurn.RUNNING, "never started")

    service.cancel(session.id)
    worker.join(timeout=20)

    assert (result["session"].planning_turn, result["session"].cancel_requested, result["session"].error) == (None, False, None)
    assert "Risposta annullata" in service.messages(session.id)[-1].content
    assert service.session_turns(session.id)[-1].cancelled


def test_a_slow_planning_turn_is_stopped_by_the_timeout(store_service, data, project):
    service = _service(store_service, data, planning_timeout=1)
    session = _start(service, "acme", _task(data), "api")

    session = _send(service, session.id, "PENSACI")

    assert (session.status, session.planning_turn) == (CopilotSessionStatus.PLANNING, None) and "Nessuna risposta" in session.error


def test_a_planning_turn_left_running_by_a_dead_worker_ends_at_restart(store_service, data, project):
    service = _service(store_service, data)
    session = service.start("acme", _task(data), "api")
    store_service.claim_next_copilot_planning_turn()  # the worker took it, then died

    assert service.fail_interrupted() == 1

    session = service.session(session.id)
    assert (session.status, session.planning_turn, session.error) == (CopilotSessionStatus.PLANNING, None, "Worker interrotto.")
    assert "Manda di nuovo il messaggio" in service.messages(session.id)[-1].content
    assert _send(service, session.id, "di nuovo").planning_turn is None  # the chat goes on


def test_a_session_needs_an_agent_task_a_repository_and_the_cli(store_service, data, project):
    service = _service(store_service, data)
    note = _task(data)
    data.save_note("acme", "appunti", "# libero")

    with pytest.raises(ValidationError):
        _start(service, "acme", "appunti.md", "api")  # not an agent task
    with pytest.raises(ValidationError):
        _start(service, "acme", note, "../fuori")
    with pytest.raises(ValidationError):
        _start(service, "acme", note, "")  # the project folder is not a repository
    with pytest.raises(UpstreamError):
        _service(store_service, data, command="definitely-not-copilot-xyz").start("acme", note, "api")


# ----------------------------------------------------------------- execution

def test_the_ok_runs_copilot_in_the_worker_without_commits_and_closes_the_task(store_service, data, project, tmp_path):
    service = _service(store_service, data)
    note = _task(data)
    session = _start(service, "acme", note, "api")
    (project / "api" / "mia-modifica.txt").write_text("mia", encoding="utf-8")

    session = service.approve(session.id)
    assert session.status == CopilotSessionStatus.QUEUED
    assert "già 1 file modificati" in service.messages(session.id)[-2].content  # the user's own change

    session = service.run_next()

    assert session.status == CopilotSessionStatus.DONE and not session.head_moved
    assert sorted(session.changed_files) == ["api/copilot.txt", "api/mia-modifica.txt"] and session.outside_files == []
    assert (project / "api" / "copilot.txt").is_file()
    assert data.agent_task("acme", note).status == TaskStatus.DONE
    execution = _turns(tmp_path, session)[-1]
    assert execution["mode"] == "autopilot" and "--allow-all-tools" in execution["args"]
    denied = [execution["args"][i + 1] for i, arg in enumerate(execution["args"]) if arg == "--deny-tool"]
    assert denied == ["shell(git commit)", "shell(git push)", "shell(git reset)"]  # global-coding-agent.yml of conftest
    assert execution["prompt"] == "Ok, procedi con il piano concordato, senza commit."
    assert service.messages(session.id)[-2].content == "Ho creato copilot.txt. Criteri soddisfatti."
    assert service.run_next() is None  # nothing else queued


def test_a_commit_during_the_execution_is_reported_not_undone(store_service, data, project):
    service = _service(store_service, data)
    session = _start(service, "acme", _task(data, "Fai COMMIT"), "api")
    head = _git(project / "api", "rev-parse", "HEAD")

    service.approve(session.id)
    session = service.run_next()

    assert session.moved_repositories == ["api"] and session.heads_before == {"api": head, "web": _git(project / "web", "rev-parse", "HEAD")}
    assert _git(project / "api", "log", "-1", "--format=%s") == "copilot"  # still there
    assert any("L'HEAD è cambiato" in message.content for message in service.messages(session.id))


def test_a_repository_without_commits_works_and_its_first_commit_is_reported(store_service, data, project):
    fresh = project / "nuovo"
    fresh.mkdir()
    _git(fresh, "init", "-q")  # no commit yet: no HEAD
    service = _service(store_service, data)

    clean = _start(service, "acme", _task(data, "Parti da zero"), "nuovo")
    service.approve(clean.id)
    clean = service.run_next()
    assert (clean.status, clean.heads_before["nuovo"], clean.heads_after["nuovo"], clean.head_moved) == (CopilotSessionStatus.DONE, "", "", False)
    assert clean.changed_files == ["nuovo/copilot.txt"]

    committed = _start(service, "acme", _task(data, "Fai COMMIT subito"), "nuovo")
    service.approve(committed.id)
    committed = service.run_next()
    assert committed.heads_before["nuovo"] == "" and committed.moved_repositories == ["nuovo"]
    assert any("nuovo: nessun commit →" in message.content for message in service.messages(committed.id))


def test_a_failed_execution_reopens_the_task_and_the_chat_can_go_on(store_service, data, project):
    service = _service(store_service, data)
    note = _task(data, "FAIL apposta")
    session = _start(service, "acme", note, "api")
    service.approve(session.id)

    session = service.run_next()

    assert session.status == CopilotSessionStatus.FAILED and "errore simulato" in session.error
    assert data.agent_task("acme", note).status == TaskStatus.TODO
    assert _send(service, session.id, "riproviamo").status == CopilotSessionStatus.PLANNING


def test_cancelling_stops_a_queued_or_running_execution(store_service, redis_client, project, tmp_path):
    store = _threaded_store(store_service, redis_client, tmp_path)
    data = ProjectDataService(store)
    service = _service(store, data)
    queued = _start(service, "acme", _task(data, "Primo"), "api")
    service.approve(queued.id)
    assert service.cancel(queued.id).status == CopilotSessionStatus.CANCELLED

    running = _start(service, "acme", _task(data, "SLEEP lungo"), "api")
    service.approve(running.id)
    result = {}
    worker = threading.Thread(target=lambda: result.update(session=service.run_next()))
    worker.start()
    _wait(lambda: service.session(running.id).status == CopilotSessionStatus.RUNNING, "never started")
    with pytest.raises(ConflictError):
        _send(service, running.id, "ehi")
    service.cancel(running.id)
    worker.join(timeout=20)

    assert result["session"].status == CopilotSessionStatus.CANCELLED
    with pytest.raises(ConflictError):
        service.cancel(running.id)


def test_a_slow_execution_is_stopped_by_the_timeout(store_service, data, project):
    service = _service(store_service, data, execution_timeout=1)
    session = _start(service, "acme", _task(data, "SLEEP"), "api")
    service.approve(session.id)

    session = service.run_next()

    assert session.status == CopilotSessionStatus.FAILED and "Nessuna risposta" in session.error


def test_one_execution_at_a_time_per_repository(store_service, data, project):
    service = _service(store_service, data)
    first, second, other = (_start(service, "acme", _task(data, title), repo)
                            for title, repo in (("Uno", "api"), ("Due", "api"), ("Tre", "web")))
    for session in (first, second, other):
        service.approve(session.id)

    claimed = store_service.claim_next_copilot_session()  # first, now running on api
    assert claimed.id == first.id
    assert store_service.claim_next_copilot_session().id == other.id  # second waits: api is busy


def test_executions_left_running_by_a_dead_worker_fail_at_restart(store_service, data, project):
    service = _service(store_service, data)
    note = _task(data)
    session = _start(service, "acme", note, "api")
    service.approve(session.id)
    store_service.claim_next_copilot_session()

    assert service.fail_interrupted() == 1
    assert service.session(session.id).status == CopilotSessionStatus.FAILED
    with pytest.raises(ConflictError):
        service.approve(session.id)  # only from planning


# -------------------------------------------------------------- repositories

def test_without_a_choice_copilot_works_on_every_repository_from_the_project_folder(store_service, data, project, tmp_path):
    service = _service(store_service, data)

    session = _start(service, "acme", _task(data), [])

    assert (session.repository, session.repositories) == ("", ["api", "web"])
    turn = _turns(tmp_path, session)[0]
    assert turn["args"][turn["args"].index("--add-dir") + 1] == str(project)  # starts in the project folder
    assert "Lavori sui repository api, web" in turn["prompt"]
    service.approve(session.id)
    session = service.run_next()
    assert session.status == CopilotSessionStatus.DONE and set(session.heads_before) == {"api", "web"}


def test_only_repositories_of_the_project_can_be_chosen(store_service, data, project):
    service = _service(store_service, data)
    note = _task(data)
    (project / "api" / "src").mkdir()

    with pytest.raises(ValidationError, match="non è un repository del progetto"):
        service.start("acme", note, ["api/src"])  # inside a repository, not one
    with pytest.raises(ValidationError):
        service.start("acme", note, ["api", "manca"])
    assert service.start("acme", note, ["web/", "api", "api"]).repositories == ["api", "web"]


def test_an_execution_locks_only_its_repositories(store_service, data, project):
    service = _service(store_service, data)
    first, both, other, third = (_start(service, "acme", _task(data, title), repos) for title, repos in
                                 (("Uno", ["api"]), ("Entrambi", ["api", "web"]), ("Web", ["web"]), ("Ancora web", ["web"])))
    for session in (first, both, other, third):
        service.approve(session.id)

    assert store_service.claim_next_copilot_session().id == first.id
    assert store_service.claim_next_copilot_session().id == other.id  # «Entrambi» waits for api, web is free
    assert store_service.claim_next_copilot_session() is None  # «Entrambi» and «Ancora web» wait


def test_files_changed_in_a_repository_not_chosen_are_reported(store_service, data, project):
    service = _service(store_service, data)
    (project / "web" / "gia-sporco.txt").write_text("mio", encoding="utf-8")
    session = _start(service, "acme", _task(data, "Scrivi FUORI"), ["api"])
    service.approve(session.id)

    session = service.run_next()

    assert session.changed_files == ["api/copilot.txt"] and session.outside_files == ["web/fuori.txt"]  # not the file dirty before
    assert any("Cambiati 1 file in repository non scelti:\n- web/fuori.txt" in message.content for message in service.messages(session.id))


def test_sessions_made_before_the_choice_keep_their_repository(store_service, data, project):
    from models.domain.copilot import CopilotSession
    service = _service(store_service, data)
    old = store_service.save_copilot_session(CopilotSession(project_name="acme", task_note=_task(data), repository="api",
                                                            copilot_session_id="vecchia", status=CopilotSessionStatus.QUEUED,
                                                            head_before="a", head_after="b"))
    assert (old.repos, old.moved_repositories) == (["api"], ["api"])
    _start(service, "acme", _task(data, "Nuova"), ["api"])
    service.approve(service.sessions("acme")[0].id)

    assert store_service.claim_next_copilot_session().id == old.id
    assert store_service.claim_next_copilot_session() is None  # api is busy with the old one


# --------------------------------------------------- coding-agent definition

def test_the_project_definition_replaces_the_global_fields_and_prompts_can_be_files(store_service, data, project, config, tmp_path):
    folder = config.definitions_root / "project" / "acme"
    folder.mkdir(parents=True)
    (folder / "piano.md").write_text("Piano su misura con {braces} JSON.\n\n{task}\n", encoding="utf-8")
    (folder / "coding-agent.yml").write_text("plan_prompt_file: piano.md\ndenied_tools: []\n", encoding="utf-8")
    service = _service(store_service, data)

    settings = service.coding_agent("acme")
    assert settings.denied_tools == [] and settings.execute_prompt.startswith("Ok, procedi")  # execute_prompt from the global
    session = _start(service, "acme", _task(data), "api")
    assert service.messages(session.id)[0].content.startswith("Piano su misura con {braces} JSON.\n\n# Aggiungi copilot.txt")
    service.approve(session.id)
    assert "--deny-tool" not in _turns(tmp_path, service.run_next())[-1]["args"]
    assert service.coding_agent().denied_tools  # other projects: the global list


def test_delegating_with_a_chosen_prompt_and_model_uses_them_for_every_turn(store_service, data, project, config, tmp_path):
    root = config.definitions_root
    (root / "global-coding-agent.yml").write_text(
        (root / "global-coding-agent.yml").read_text(encoding="utf-8") + "models: [gpt-5, claude-sonnet-4.5]\n", encoding="utf-8")
    (root / "coding-agent").mkdir()
    (root / "coding-agent" / "refactor.md").write_text("Solo refactoring.\n{task}", encoding="utf-8")
    (root / "coding-agent" / "bug.md").write_text("Trova il bug.\n{task}", encoding="utf-8")
    (root / "coding-agent" / "note.txt").write_text("non è un prompt", encoding="utf-8")
    (root / "project" / "acme" / "coding-agent").mkdir(parents=True)
    (root / "project" / "acme" / "coding-agent" / "bug.md").write_text("Bug, a modo di acme.\n{task}", encoding="utf-8")
    service = _service(store_service, data)

    assert list(service.coding_agent("acme").prompts) == ["bug", "refactor"]
    assert service.coding_agent("acme").prompts["bug"].startswith("Bug, a modo di acme.")  # the project's wins
    session = _start(service, "acme", _task(data), "api", prompt="bug", model="gpt-5")
    _send(service, session.id, "ok")
    service.approve(session.id)
    session = service.run_next()

    assert (session.prompt, session.model) == ("bug", "gpt-5")
    assert service.messages(session.id)[0].content.startswith("Bug, a modo di acme.\n# Aggiungi copilot.txt")
    turns = _turns(tmp_path, session)
    assert len(turns) == 3 and all(turn["args"][turn["args"].index("--model") + 1] == "gpt-5" for turn in turns)
    with pytest.raises(ValidationError, match="Modello non previsto"):
        _start(service, "acme", _task(data, "Altro"), "api", model="gpt-4")
    with pytest.raises(ValidationError, match="Prompt non trovato"):
        _start(service, "acme", _task(data, "Altro ancora"), "api", prompt="manca")
    assert "--model" not in _turns(tmp_path, _start(service, "acme", _task(data, "Default"), "api"))[0]["args"]


def test_a_prompt_file_without_the_task_placeholder_is_an_error(store_service, data, project, config):
    (config.definitions_root / "coding-agent").mkdir()
    (config.definitions_root / "coding-agent" / "rotto.md").write_text("Niente segnaposto", encoding="utf-8")

    assert "coding-agent/rotto.md deve contenere {task}" in _service(store_service, data).coding_agent_or_error()[1]


@pytest.mark.parametrize("text, error", [
    (None, "Manca definition/global-coding-agent.yml"),
    ("plan_prompt: senza segnaposto\nexecute_prompt: vai\ndenied_tools: []\n", "{task}"),
    ("plan_prompt: '{task}'\ndenied_tools: []\n", "manca execute_prompt"),
    ("plan_prompt: '{task}'\nexecute_prompt: vai\ndenied_tools: []\ndenyed: []\n", "denyed"),
    ("plan_prompt: '{task}'\nplan_prompt_file: p.md\nexecute_prompt: vai\ndenied_tools: []\n", "uno dei due"),
    ("plan_prompt_file: manca.md\nexecute_prompt: vai\ndenied_tools: []\n", "non trovato o vuoto"),
    ("plan_prompt: [rotto\n", "YAML non valido"),
])
def test_a_missing_or_broken_global_definition_stops_copilot(store_service, data, project, config, text, error):
    path = config.definitions_root / "global-coding-agent.yml"
    path.unlink()
    if text is not None:
        path.write_text(text, encoding="utf-8")
    service = _service(store_service, data)

    assert error in service.coding_agent_or_error("acme")[1]
    with pytest.raises(ValidationError, match=error.replace("{", r"\{").replace("}", r"\}")):
        _start(service, "acme", _task(data), "api")


def test_an_execution_fails_when_the_definition_broke_after_the_ok(store_service, data, project, config):
    service = _service(store_service, data)
    session = _start(service, "acme", _task(data), "api")
    service.approve(session.id)
    (config.definitions_root / "global-coding-agent.yml").unlink()

    session = service.run_next()

    assert session.status == CopilotSessionStatus.FAILED and "Manca definition/global-coding-agent.yml" in session.error


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

    CopilotClient(FAKE).turn(tmp_path, "s2", "vai", CopilotMode.PLAN, 30, denied_tools=["shell(git commit)"])
    assert "--deny-tool" not in json.loads((tmp_path / "state" / "s2.json").read_text(encoding="utf-8"))[-1]["args"]  # plan mode: no denials


# --------------------------------------------------------------------- usage

def test_each_turn_records_what_it_used_out_of_the_session_totals(store_service, data, project, config):
    (config.definitions_root / "global-coding-agent.yml").write_text(
        (config.definitions_root / "global-coding-agent.yml").read_text(encoding="utf-8") + "models: [gpt-5]\n", encoding="utf-8")
    service = _service(store_service, data)
    session = _start(service, "acme", _task(data), "api", model="gpt-5")
    _send(service, session.id, "ok")
    service.approve(session.id)
    service.run_next()

    turns = service.session_turns(session.id)

    assert [turn.phase.value for turn in turns] == ["plan", "plan", "execute"]
    assert all(turn.model == "gpt-5" and turn.ok and turn.duration_ms > 0 for turn in turns)
    # the fake reports cumulative totals (1, 2, 3 turns): each row holds one turn's share
    assert [(turn.usage.premium_requests, turn.usage.nano_aiu, turn.usage.input_tokens) for turn in turns] == [(1, 100_000_000, 1000)] * 3
    (by_model,) = service.usage_by_model(days=30, project_name="acme")
    assert (by_model.model, by_model.turns, by_model.usage.output_tokens, round(by_model.usage.ai_credits, 2)) == ("gpt-5", 3, 30, 0.3)
    service.delete(session.id)
    assert len(service.recent_turns(project_name="acme")) == 3  # the history outlives the session


def test_a_turn_killed_before_writing_its_usage_records_none(store_service, data, project):
    service = _service(store_service, data, execution_timeout=1)
    session = _start(service, "acme", _task(data, "SLEEP"), "api")
    service.approve(session.id)
    service.run_next()

    plan, execute = service.session_turns(session.id)

    assert plan.usage.premium_requests == 1 and plan.model == "fake-default"
    assert (execute.ok, execute.usage.premium_requests, execute.usage.nano_aiu) == (False, 0, 0)
    assert "Nessuna risposta" in execute.error


def test_usage_since_takes_the_difference_or_everything_after_a_reset():
    from models.domain.copilot import CopilotUsage
    before, after = CopilotUsage(premium_requests=2, nano_aiu=10, input_tokens=100), CopilotUsage(premium_requests=3, nano_aiu=25, input_tokens=180)

    assert after.since(before) == CopilotUsage(premium_requests=1, nano_aiu=15, input_tokens=80)
    assert before.since(after) == before  # totals went down: Copilot counts again from zero


def test_the_usage_file_is_read_as_copilot_writes_it(tmp_path):
    """Trimmed from a real ``--usage-output-file`` of Copilot CLI 1.0.103."""
    from domain.client.copilot.usage import read_usage
    path = tmp_path / "usage.json"
    path.write_text(json.dumps({
        "totalPremiumRequestCost": 1, "totalUserRequests": 1, "totalNanoAiu": 339040000, "aiCreditsStatus": "complete",
        "tokenDetails": {"input": {"tokenCount": 4}, "cache_read": {"tokenCount": 0}, "cache_write": {"tokenCount": 26732}, "output": {"tokenCount": 97}},
        "totalApiDurationMs": 2842,
        "modelMetrics": {"claude-haiku-5.5": {
            "requests": {"count": 1, "cost": 1},
            "usage": {"inputTokens": 26736, "outputTokens": 97, "cacheReadTokens": 0, "cacheWriteTokens": 26732, "reasoningTokens": 92},
            "totalNanoAiu": 339040000,
        }},
        "currentModel": "claude-haiku-5.5",
    }), encoding="utf-8")

    usage, model = read_usage(path)

    assert model == "claude-haiku-5.5" and round(usage.ai_credits, 4) == 0.339
    assert (usage.premium_requests, usage.input_tokens, usage.output_tokens,
            usage.cache_write_tokens, usage.reasoning_tokens, usage.api_duration_ms) == (1, 26736, 97, 26732, 92, 2842)
    assert read_usage(tmp_path / "manca.json") == (None, "")
    (tmp_path / "rotto.json").write_text("{non json", encoding="utf-8")
    assert read_usage(tmp_path / "rotto.json") == (None, "")


def test_models_come_with_their_price_cheapest_first_and_what_they_cost_so_far(store_service, data, project, config):
    path = config.definitions_root / "global-coding-agent.yml"
    path.write_text(path.read_text(encoding="utf-8") + """models:
  - auto
  - {name: caro, input: 4, cached_input: 0.2, cache_write: 5, output: 20, note: per i task difficili}
  - {name: economico, input: 0.1, cached_input: 0.01, cache_write: 0.125, output: 0.5,
     long_context: {above: 100000, input: 0.5, cached_input: 0.05, cache_write: 0.625, output: 2.5}}
  - {name: senza-cache-write, input: 2, cached_input: 0.1, output: 10}
""", encoding="utf-8")
    service = _service(store_service, data)
    session = _start(service, "acme", _task(data), "api", model="economico")
    _send(service, session.id, "ok")

    options = service.model_options(service.coding_agent("acme"))

    assert [model.name for model, _ in options] == ["economico", "senza-cache-write", "caro", "auto"]
    economico, usage = options[0]
    assert (economico.long_context_above, economico.long_context_price.output) == (100000, 2.5)
    assert (usage.turns, round(usage.usage.ai_credits, 2)) == (2, 0.2)
    assert options[1][0].price.cache_write is None and options[2][0].note == "per i task difficili"
    assert options[3][0].price is None and options[3][1] is None  # a plain name: no price, never used


@pytest.mark.parametrize("models, error", [
    ("[{name: x, input: 1}]", "insieme"),
    ("[{name: x, input: 1, output: 2, prezzo: 3}]", "prezzo"),
    ("[x, {name: x, input: 1, output: 2}]", "modelli ripetuti in models: x"),
    ("[{name: x, output: 1, input: 1, long_context: {input: 2, cached_input: 0, output: 3}}]", "above"),
])
def test_a_wrong_model_price_is_an_error(store_service, data, project, config, models, error):
    path = config.definitions_root / "global-coding-agent.yml"
    path.write_text(path.read_text(encoding="utf-8") + f"models: {models}\n", encoding="utf-8")

    assert error in _service(store_service, data).coding_agent_or_error()[1]


def test_deleting_a_tasks_sessions_keeps_the_others_and_the_usage(store_service, data, project):
    service = _service(store_service, data)
    note, other = _task(data), _task(data, "Altro")
    first, second = _start(service, "acme", note, "api"), _start(service, "acme", note, "web")
    kept = _start(service, "acme", other, "api")
    service.approve(second.id)

    with pytest.raises(ConflictError):
        service.delete_task_sessions("acme", note)  # one is queued: nothing deleted
    assert len(service.sessions("acme")) == 3
    service.cancel(second.id)

    assert service.delete_task_sessions("acme", note.removesuffix(".md")) == 2  # the note's name, with or without .md
    assert [session.id for session in service.sessions("acme")] == [kept.id]
    assert {turn.session_id for turn in service.recent_turns(project_name="acme")} == {first.id, second.id, kept.id}
    assert service.delete_task_sessions("acme", note) == 0


# --------------------------------------------------------------- task folder

def test_copilot_reads_the_task_and_its_references_from_a_folder_rebuilt_every_turn(store_service, data, project, config, tmp_path):
    from models.domain.note import NoteType, Reference

    path = config.definitions_root / "global-coding-agent.yml"
    path.write_text(path.read_text(encoding="utf-8") + "references_prompt: 'I riferimenti sono in {task_folder}.'\n", encoding="utf-8")
    service = _service(store_service, data)
    ref = data.create_reference("acme", NoteType.CODE_REFERENCE, Reference(title="Login", path="src/a.py", content="v1"))
    note = data.create_agent_task("acme", AgentTask(title="Con riferimenti", references=[ref, "context-reference-sparito.md"]))

    session = _start(service, "acme", note, "api")

    turn = _turns(tmp_path, session)[0]
    folder = Path(turn["args"][[i for i, arg in enumerate(turn["args"]) if arg == "--add-dir"][1] + 1])
    assert turn["prompt"].endswith(f"I riferimenti sono in {folder}.")
    assert sorted(item.name for item in folder.iterdir()) == ["code-reference-login.md", "task.md"]  # the missing one is skipped
    assert "# Con riferimenti" in (folder / "task.md").read_text(encoding="utf-8")

    data.save_reference("acme", ref, Reference(title="Login", path="src/a.py", content="v2"))
    _send(service, session.id, "e adesso?")
    assert "v2" in (folder / "code-reference-login.md").read_text(encoding="utf-8")  # always current
    assert _turns(tmp_path, session)[1]["args"].count("--add-dir") == 2

    service.delete(session.id)
    assert not folder.exists()


def test_without_references_nothing_is_added_and_a_deleted_task_still_lets_the_chat_go_on(store_service, data, project, tmp_path):
    service = _service(store_service, data)
    note = _task(data)
    session = _start(service, "acme", note, "api")
    assert "riferimenti" not in _turns(tmp_path, session)[0]["prompt"].lower()

    data.delete_note("acme", note)
    session = _send(service, session.id, "ci sei?")

    assert session.status == CopilotSessionStatus.PLANNING and _turns(tmp_path, session)[-1]["args"].count("--add-dir") == 1


def test_a_references_prompt_needs_the_task_folder_placeholder(store_service, data, project, config):
    path = config.definitions_root / "global-coding-agent.yml"
    path.write_text(path.read_text(encoding="utf-8") + "references_prompt: senza segnaposto\n", encoding="utf-8")

    assert "{task_folder}" in _service(store_service, data).coding_agent_or_error()[1]
