"""Copilot and the app's MCP server: the session's token, the tools (task,
references, ask_user, finish), the check before every turn, and the whole
loop with a real server (uvicorn) and the fake Copilot CLI calling it."""
import json
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from sqlmodel import SQLModel, create_engine

from core.app import create_app
from core.container import Container
from core.error import ConflictError, NotFoundError, UpstreamError, ValidationError
from domain.client.copilot.client import CopilotClient, McpAccess
from models.domain.copilot import CopilotMessageRole, CopilotSessionStatus
from models.domain.note import AgentTask, NoteType, Reference, TaskStatus, TaskType
from models.domain.project import Project, ProjectSource
from service.copilot_service import CopilotService, mcp_unreachable, mcp_url
from service.git_service import GitService

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

FAKE = [sys.executable, str(Path(__file__).parents[2] / "fake_copilot.py")]


@pytest.fixture
def engine(tmp_path):
    """A SQLite file, one connection per thread: here the API, the worker and
    ask_user write at the same time (the shared in-memory connection of the
    other tests would mix their transactions; Postgres has a pool)."""
    engine = create_engine(f"sqlite:///{tmp_path / 'app.db'}", connect_args={"check_same_thread": False, "timeout": 30})
    SQLModel.metadata.create_all(engine)
    return engine


def _git(cwd, *args) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def project(tmp_path, monkeypatch, project_store):
    """Project ``acme`` with the repository ``api`` (one commit)."""
    monkeypatch.setenv("FAKE_COPILOT_STATE", str(tmp_path / "copilot-state"))
    repo = tmp_path / "acme" / "api"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    (repo / "README.md").write_text("api", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.name=A", "-c", "user.email=a@b.it", "commit", "-qm", "init")
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path=str(tmp_path / "acme")))
    return tmp_path / "acme"


def _service(stores, data, url: str | None = None, check=None, ask_timeout: float = 5.0) -> CopilotService:
    return CopilotService(stores.definitions, stores.copilot, GitService(stores.projects), data, CopilotClient(FAKE),
                          planning_timeout_seconds=60, execution_timeout_seconds=60, mcp_url=url, mcp_check=check,
                          ask_user_timeout_seconds=ask_timeout, poll_seconds=0.02)


def _task(data, title="Prova", **fields) -> str:
    return data.create_agent_task("acme", AgentTask(title=title, objective="Obiettivo segreto", **{"status": TaskStatus.TODO, **fields}))


def _running(service, data, stores, title="Prova", **fields):
    """A session whose execution is running (the worker would be inside the turn)."""
    session = service.start("acme", _task(data, title, **fields), "api")
    return stores.copilot.update_session(session.id, status=CopilotSessionStatus.RUNNING)


# ------------------------------------------------------------- the tools

def test_every_session_has_its_own_token_and_the_tools_see_only_its_task(project, project_data_service, stores):
    data = project_data_service
    service = _service(stores, data)
    reference = data.create_reference("acme", NoteType.CODE_REFERENCE, Reference(title="Login", content="def login(): ..."))
    first = service.start("acme", _task(data, references=[reference]), "api")
    second = service.start("acme", _task(data, "Altro"), "api")

    assert first.mcp_token and second.mcp_token and first.mcp_token != second.mcp_token
    task = service.mcp_task(first.mcp_token)
    assert (task["title"], task["type"], task["objective"], task["checklist"]) == ("Prova", "development", "Obiettivo segreto", [])
    assert [link.name for link in service.mcp_links(first.mcp_token)] == [reference]
    assert service.mcp_link(first.mcp_token, reference).startswith("# Login")
    with pytest.raises(NotFoundError):
        service.mcp_link(second.mcp_token, reference)  # not linked to the other task
    assert service.mcp_task(second.mcp_token)["title"] == "Altro"

    for token in ("", "inventato"):
        with pytest.raises(ValidationError, match="Token MCP non valido"):
            service.mcp_task(token)
    service.delete(first.id)
    with pytest.raises(ValidationError):
        service.mcp_task(first.mcp_token)  # gone with its session


def test_the_checklist_of_the_task_s_type_comes_with_it(project, project_data_service, stores, config):
    path = config.definitions_root / "global-coding-agent.yml"
    path.write_text(path.read_text(encoding="utf-8") + "task_checklists:\n  development: [repository, criteri]\n", encoding="utf-8")
    service = _service(stores, project_data_service)

    session = service.start("acme", _task(project_data_service), "api")

    assert service.mcp_task(session.mcp_token)["checklist"] == ["repository", "criteri"]


def test_ask_user_waits_for_the_answer_from_the_chat(project, project_data_service, stores):
    service = _service(stores, project_data_service)
    session = _running(service, project_data_service, stores)
    answers: list[str] = []
    asking = threading.Thread(target=lambda: answers.append(service.ask_user(session.mcp_token, " Che nome uso? ")))

    asking.start()
    deadline = time.monotonic() + 5
    while service.pending_question(session.id) is None and time.monotonic() < deadline:
        time.sleep(0.02)
    assert service.pending_question(session.id).content == "Che nome uso?"
    service.answer(session.id, "  Ada  ")
    asking.join(5)

    assert answers == ["Ada"]
    assert service.pending_question(session.id) is None
    assert [m.role for m in service.messages(session.id)][-2:] == [CopilotMessageRole.QUESTION, CopilotMessageRole.USER]


def test_ask_user_without_an_answer_or_cancelled_or_while_planning(project, project_data_service, stores):
    service = _service(stores, project_data_service, ask_timeout=0.1)
    planning = service.start("acme", _task(project_data_service, "In preparazione"), "api")
    assert "scrivi la domanda nella tua risposta" in service.ask_user(planning.mcp_token, "Domanda?")
    with pytest.raises(ValidationError, match="vuota"):
        service.ask_user(planning.mcp_token, "  ")

    session = _running(service, project_data_service, stores)
    assert "Nessuna risposta: decidi tu" in service.ask_user(session.mcp_token, "Ci sei?")
    assert "Nessuna risposta in tempo" in service.messages(session.id)[-1].content

    stores.copilot.update_session(session.id, cancel_requested=True)
    assert "Esecuzione annullata" in service.ask_user(session.mcp_token, "E adesso?")


def test_answering_needs_a_pending_question_during_an_execution(project, project_data_service, stores):
    service = _service(stores, project_data_service)
    session = _running(service, project_data_service, stores)

    with pytest.raises(ConflictError, match="non ti ha fatto domande"):
        service.answer(session.id, "risposta")
    with pytest.raises(ValidationError, match="vuota"):
        service.answer(session.id, " ")
    stores.copilot.add_message(service.messages(session.id)[0].model_copy(update={"id": None, "role": CopilotMessageRole.QUESTION}))
    stores.copilot.update_session(session.id, status=CopilotSessionStatus.DONE)
    with pytest.raises(ConflictError):
        service.answer(session.id, "troppo tardi")  # the execution is over


def test_finish_says_done_and_a_development_becomes_to_verify(project, project_data_service, stores):
    data = project_data_service
    service = _service(stores, data)
    development = _running(service, data, stores)
    analysis = _running(service, data, stores, "Analisi", type=TaskType.ANALYSIS)
    planning = service.start("acme", _task(data, "Ancora in preparazione"), "api")

    assert "Ricevuto" in service.finish(development.mcp_token, "  Ho cambiato login.py.  ")
    assert service.messages(development.id)[-1].content == "🏁 Ho cambiato login.py."
    assert data.agent_task("acme", development.task_note).status == TaskStatus.TO_VERIFY
    service.finish(analysis.mcp_token, "")
    assert service.messages(analysis.id)[-1].content == "🏁 Fatto."
    assert data.agent_task("acme", analysis.task_note).status != TaskStatus.TO_VERIFY  # plan-only: saved as a note instead
    assert "Non sei in esecuzione" in service.finish(planning.mcp_token, "fatto")
    data.delete_note("acme", development.task_note)
    assert "non esiste più" in service.finish(development.mcp_token, "di nuovo")


# ------------------------------------------- the CLI and the check before a turn

def test_every_turn_gives_copilot_the_mcp_server_with_the_session_s_token(project, project_data_service, stores, tmp_path):
    service = _service(stores, project_data_service, url="http://localhost:9/api/mcp/")
    session = service.start("acme", _task(project_data_service, "Senza il server nel titolo"), "api")
    service.approve(session.id)
    service.run_next()

    turns = json.loads((tmp_path / "copilot-state" / f"{session.copilot_session_id}.json").read_text(encoding="utf-8"))
    for turn in turns:  # planning and execution
        args = turn["args"]
        assert args[args.index("--allow-tool") + 1] == "mbare-pilot"
        assert args[args.index("--additional-mcp-config") + 1].startswith("@")  # a file: the token is not on the command line
        assert session.mcp_token not in " ".join(args)
    assert McpAccess("http://x/mcp/", "t").config() == {"mcpServers": {"mbare-pilot": {
        "type": "http", "url": "http://x/mcp/", "headers": {"Authorization": "Bearer t"}, "tools": ["*"]}}}


def test_without_the_mcp_server_no_turn_starts(project, project_data_service, stores):
    reachable = {"yes": True}
    service = _service(stores, project_data_service, url="http://localhost:9/api/mcp/",
                       check=lambda url: None if reachable["yes"] else "connessione rifiutata")
    session = service.start("acme", _task(project_data_service), "api")
    reachable["yes"] = False

    with pytest.raises(UpstreamError, match="non risponde su http://localhost:9/api/mcp/: connessione rifiutata"):
        service.start("acme", _task(project_data_service, "Un altro"), "api")
    with pytest.raises(UpstreamError):
        service.send(session.id, "ci sei?")
    service.approve(session.id)
    failed = service.run_next()
    assert failed.status == CopilotSessionStatus.FAILED and "non risponde" in failed.error
    assert len(service.sessions("acme")) == 1  # nothing saved for the refused start


def test_the_ping_and_the_url(monkeypatch):
    assert mcp_url("http://127.0.0.1:8000/") == "http://127.0.0.1:8000/api/mcp/"
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: httpx.Response(200))
    assert mcp_unreachable("http://x/mcp/") is None
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: httpx.Response(404))
    assert mcp_unreachable("http://x/mcp/") == "risposta 404"

    def refused(*args, **kwargs):
        raise httpx.ConnectError("connessione rifiutata")

    monkeypatch.setattr(httpx, "post", refused)
    assert mcp_unreachable("http://x/mcp/") == "connessione rifiutata"


# ------------------------------------------------------ the whole loop

@pytest.fixture
def server(stores, project, monkeypatch):
    """The API on a free port, in a thread: Copilot (the fake CLI, a separate process) calls its MCP server."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    container = Container(stores=stores)
    url = f"http://127.0.0.1:{port}/mcp/"
    container.copilot_service = _service(stores, container.project_data_service, url=url, check=mcp_unreachable)
    running = uvicorn.Server(uvicorn.Config(create_app(container), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=running.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not running.started and time.monotonic() < deadline:
        time.sleep(0.02)
    yield container, f"http://127.0.0.1:{port}"
    running.should_exit = True
    thread.join(10)


def test_copilot_reads_the_task_asks_and_finishes_through_the_real_server(server, project):
    container, base = server
    service, data = container.copilot_service, container.project_data_service
    reference = data.create_reference("acme", NoteType.CONTEXT_REFERENCE, Reference(title="Specifiche", content="..."))
    note = _task(data, "VIAMCP ASK nome", references=[reference])

    # the planning turn runs inside an API request, and Copilot calls the same API back: no deadlock
    created = httpx.post(f"{base}/projects/acme/copilot-sessions", json={"task_note": note, "repository": "api"}, timeout=60)
    assert created.status_code == 201, created.text
    session = service.session(created.json()["id"])
    assert service.messages(session.id)[-1].content == "Ho letto via MCP: Obiettivo segreto (1 riferimenti)"

    service.approve(session.id)
    worker = threading.Thread(target=service.run_next)
    worker.start()
    deadline = time.monotonic() + 30
    while service.pending_question(session.id) is None and time.monotonic() < deadline:
        time.sleep(0.05)
    assert service.pending_question(session.id).content == "Che nome uso?"
    answered = httpx.post(f"{base}/copilot-sessions/{session.id}/answer", json={"text": "Ada"}, timeout=10)
    assert answered.status_code == 200
    worker.join(30)

    assert (project / "api" / "copilot.txt").read_text(encoding="utf-8") == "scritto da Copilot via MCP: Ada\n"
    contents = [message.content for message in service.messages(session.id)]
    assert "🏁 Creato copilot.txt (Ada)." in contents
    assert data.agent_task("acme", note).status == TaskStatus.TO_VERIFY
    assert service.session(session.id).status == CopilotSessionStatus.DONE


def test_copilot_searches_the_project_s_context(server):
    container, base = server
    data, service = container.project_data_service, container.copilot_service
    data.save_context("acme", "convenzioni", "# Convenzioni\n\n## Branch\nI branch si chiamano feature/<ticket>.")
    container.rag_service.reindex("acme")
    session = service.start("acme", _task(data), "api")
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "search_context", "arguments": {"question": "Come si chiamano i branch?"}}}
    headers = {"Accept": "application/json, text/event-stream", "Authorization": f"Bearer {session.mcp_token}"}

    result = httpx.post(f"{base}/mcp/", json=body, headers=headers, timeout=10).json()["result"]

    [hit] = result["structuredContent"]["result"]
    assert (hit["path"], hit["section"]) == ("context/convenzioni.md", "Branch")


def test_the_server_refuses_a_wrong_token(server):
    _, base = server
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "read_task", "arguments": {}}}
    headers = {"Accept": "application/json, text/event-stream", "Authorization": "Bearer sbagliato"}

    result = httpx.post(f"{base}/mcp/", json=body, headers=headers, timeout=10).json()["result"]

    assert result["isError"] and "Token MCP non valido" in result["content"][0]["text"]
    tools = httpx.post(f"{base}/mcp/", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, headers=headers, timeout=10).json()
    assert sorted(tool["name"] for tool in tools["result"]["tools"]) == [
        "ask_user", "finish", "list_references", "read_reference", "read_task", "search_context"]
