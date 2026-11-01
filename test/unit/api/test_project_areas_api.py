"""Chat, Dati, Git, Automation, Atlassian and Admin endpoints over the
in-memory store; agents are faked, git runs on a tmp repository."""
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.container import Container
from fakes import FakeAgent, make_run_record
from models.domain.atlassian import ConfluencePage, ConfluenceSearchHit, ConfluenceSpace, JiraIssue
from models.domain.project import Project, ProjectSource
from service import agent_service as agent_service_module
from service.atlassian_service import AtlassianSite
from service.backup_service import BackupService

MODEL = "openai/gpt-4o"


@pytest.fixture
def project_root(tmp_path):
    root = tmp_path / "acme"
    root.mkdir()
    return root


@pytest.fixture
def client(stores, project_root, monkeypatch, project_store):
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path=str(project_root)))
    monkeypatch.setattr(agent_service_module.AgentFactory, "create_agent",
                        staticmethod(lambda definition, client, tools: FakeAgent(None)))
    container = Container(stores=stores)
    monkeypatch.setattr(container.chat_service, "get_client", lambda model: object())
    with TestClient(create_app(container)) as client:
        yield client


# --------------------------------------------------------------------- chat

def _chatbot(client, name="Bot", **overrides) -> dict:
    body = {"name": name, "system_prompt": "Sei l'assistente.", "model": MODEL, "tool_names": ["hello_world"]}
    body.update(overrides)
    response = client.post("/projects/acme/chatbots", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_chatbot_crud_and_prompt_version(client):
    bot = _chatbot(client)
    assert [b["name"] for b in client.get("/projects/acme/chatbots").json()] == ["Bot", "Chat bot", "Segretario"]  # plus the default ones

    body = {"name": "Bot 2", "system_prompt": "Nuovo prompt.", "model": MODEL, "max_steps": 6}
    updated = client.put(f"/chatbots/{bot['id']}", json=body).json()
    assert (updated["name"], updated["prompt_version"], updated["max_steps"]) == ("Bot 2", 2, 6)

    assert client.post("/projects/acme/chatbots", json={**body, "model": "nope"}).status_code == 400
    assert client.delete(f"/chatbots/{bot['id']}").status_code == 204
    assert client.delete(f"/chatbots/{bot['id']}").status_code == 404


def test_only_the_model_of_a_chatbot_changes(client):
    bot = _chatbot(client)

    changed = client.patch(f"/chatbots/{bot['id']}/model", json={"model": "mock/echo"})

    assert changed.status_code == 200, changed.text
    assert changed.json() == {**bot, "model": "mock/echo"}  # prompt, its version and tools stay
    assert client.get("/projects/acme/chatbots").json()[0]["model"] == "mock/echo"
    assert client.patch(f"/chatbots/{bot['id']}/model", json={"model": "nope"}).status_code == 400
    assert client.patch("/chatbots/999/model", json={"model": "mock/echo"}).status_code == 404


def test_conversation_send_and_messages(client):
    bot = _chatbot(client)
    conversation = client.post(f"/chatbots/{bot['id']}/conversations").json()

    reply = client.post(f"/conversations/{conversation['id']}/messages", json={"text": "Ciao"})

    assert reply.status_code == 200 and reply.json()["role"] == "assistant"
    roles = [m["role"] for m in client.get(f"/conversations/{conversation['id']}/messages").json()]
    assert roles == ["user", "assistant"]
    assert client.get(f"/chatbots/{bot['id']}/conversations").json()[0]["title"] == "Ciao"
    assert client.post(f"/conversations/{conversation['id']}/messages", json={"text": " "}).status_code == 400
    assert client.delete(f"/conversations/{conversation['id']}").status_code == 204


# --------------------------------------------------------------------- data

def test_notes_crud(client):
    assert client.put("/projects/acme/notes/Setup", json={"content": "# Setup"}).json()["name"] == "Setup.md"
    assert client.get("/projects/acme/notes/Setup.md").json() == {"name": "Setup.md", "content": "# Setup"}
    assert [n["name"] for n in client.get("/projects/acme/notes").json()] == ["Setup.md"]

    assert client.delete("/projects/acme/notes/Setup").status_code == 204
    assert client.get("/projects/acme/notes/Setup.md").status_code == 404
    assert client.put("/projects/acme/notes/.hidden", json={"content": ""}).status_code == 400


def test_references_linked_from_a_task_and_a_todo_list(client):
    ref = client.post("/projects/acme/references", json={"kind": "code_reference", "title": "Login", "path": "src/a.py", "source": "jira"})
    assert ref.status_code == 201 and ref.json()["name"] == "code-reference-login.md"
    assert client.post("/projects/acme/references", json={"kind": "todo_list", "title": "x"}).status_code == 422
    client.post("/projects/acme/agent-tasks", json={"title": "Fix", "references": ["code-reference-login.md"]})
    client.post("/projects/acme/todo-lists", json={"title": "Giro", "references": ["code-reference-login.md"]})
    assert client.post("/projects/acme/agent-tasks", json={"title": "Altro", "references": ["appunti.md"]}).status_code == 400

    [listed] = client.get("/projects/acme/references").json()
    assert (listed["path"], listed["source"], listed["linked_from"]) == ("src/a.py", "jira", ["agent-task-fix.md", "todo-list-giro.md"])
    assert client.put("/projects/acme/references/code-reference-login.md", json={"title": "Login v2"}).json()["linked_from"] == [
        "agent-task-fix.md", "todo-list-giro.md",
    ]
    assert [note["note_type"] for note in client.get("/projects/acme/notes").json() if note["name"].startswith("code-")] == ["code_reference"]

    assert client.delete("/projects/acme/references/code-reference-login.md").status_code == 204
    assert client.get("/projects/acme/agent-tasks").json()[0]["references"] == []
    assert client.delete("/projects/acme/references/code-reference-login.md").status_code == 404


def test_data_settings(client):
    assert client.get("/projects/acme/data-settings").json() == {"visible_note_types": ["generic", "agent_task", "todo_list"]}
    saved = client.put("/projects/acme/data-settings", json={"visible_note_types": ["code_reference", "generic"]})
    assert saved.json() == {"visible_note_types": ["generic", "code_reference"]}
    assert client.put("/projects/acme/data-settings", json={"visible_note_types": ["boh"]}).status_code == 422
    assert client.get("/projects/acme").json()["name"] == "acme"


def test_agent_tasks_and_todo_lists(client):
    created = client.post("/projects/acme/agent-tasks", json={"title": "Fix porto", "criteria": [{"text": "test verdi"}]})
    assert created.status_code == 201 and created.json()["name"] == "agent-task-fix-porto.md"
    assert client.post("/projects/acme/agent-tasks", json={"title": "Fix porto"}).status_code == 409
    assert client.post("/projects/acme/agent-tasks", json={"title": ""}).status_code == 422

    saved = client.put("/projects/acme/agent-tasks/agent-task-fix-porto.md", json={"title": "Fix porto", "status": "done"})
    assert saved.json()["status"] == "done"
    assert [task["status"] for task in client.get("/projects/acme/agent-tasks").json()] == ["done"]

    todo = {"title": "Rilascio", "items": [{"text": "tag", "priority": "high", "due": "2026-11-02"}]}
    assert client.post("/projects/acme/todo-lists", json=todo).json()["name"] == "todo-list-rilascio.md"
    assert client.get("/projects/acme/todo-lists").json()[0]["items"] == [{"text": "tag", "done": False, "priority": "high", "due": "2026-11-02"}]
    assert client.put("/projects/acme/todo-lists/agent-task-fix-porto.md", json=todo).status_code == 400

    types = {note["name"]: note["note_type"] for note in client.get("/projects/acme/notes").json()}
    assert types == {"agent-task-fix-porto.md": "agent_task", "todo-list-rilascio.md": "todo_list"}
    assert client.delete("/projects/acme/notes/todo-list-rilascio.md").status_code == 204


def test_files_upload_download_delete(client):
    data = bytes(range(256))
    uploaded = client.put("/projects/acme/files/report.bin", content=data).json()
    assert (uploaded["name"], uploaded["kind"], uploaded["size"]) == ("report.bin", "file", 256)

    assert client.get("/projects/acme/files/report.bin").content == data
    assert [f["name"] for f in client.get("/projects/acme/files").json()] == ["report.bin"]
    assert client.delete("/projects/acme/files/report.bin").status_code == 204
    assert client.get("/projects/acme/files/report.bin").status_code == 404


# ---------------------------------------------------------------------- git

def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_git_repositories_log_and_status(client, project_root):
    repo = project_root / "api"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Ada")
    _git(repo, "config", "user.email", "ada@example.com")
    (repo / "main.py").write_text("print()", encoding="utf-8")
    _git(repo, "add", "main.py")
    _git(repo, "commit", "-q", "-m", "first")
    (repo / "new.py").write_text("", encoding="utf-8")

    assert client.get("/projects/acme/git/repositories").json() == [{"path": "api", "name": "api"}]
    [commit] = client.get("/projects/acme/git/log", params={"path": "api"}).json()
    assert (commit["subject"], commit["author"]) == ("first", "Ada")
    status = client.get("/projects/acme/git/status", params={"path": "api"}).json()
    assert not status["is_clean"] and status["changes"][0]["kind"] == "untracked"
    assert client.get("/projects/acme/git/log", params={"path": "api", "commit": "zz"}).status_code == 400


# --------------------------------------------------------------- automation

def _pipeline_body(**overrides) -> dict:
    body = {"name": "Flow", "description": "", "active": True, "steps": [
        {"name": "Scrivi", "kind": "agent", "input_template": "{input}",
         "agent": {"system_prompt": "Scrivi.", "model": MODEL, "max_steps": 4, "tool_names": []}},
        {"name": "Nota", "kind": "function", "input_template": "{input}", "function_name": "save_note",
         "params": {"title": "Report"}},
    ]}
    body.update(overrides)
    return body


def test_pipeline_crud_and_runs(client):
    created = client.post("/projects/acme/pipelines", json=_pipeline_body())
    assert created.status_code == 201, created.text
    pipeline = created.json()
    assert [s["kind"] for s in pipeline["steps"]] == ["agent", "function"]
    assert pipeline["steps"][1]["params"]["title"] == "Report"

    renamed = client.put(f"/pipelines/{pipeline['id']}", json=_pipeline_body(name="Flow 2")).json()
    assert renamed["name"] == "Flow 2"
    assert client.post("/projects/acme/pipelines", json=_pipeline_body(name="Flow 2")).status_code == 409

    run = client.post(f"/pipelines/{pipeline['id']}/runs", json={"input": "ciao"}).json()
    assert (run["status"], run["input"]) == ("queued", "ciao")
    assert [r["id"] for r in client.get(f"/pipelines/{pipeline['id']}/runs").json()] == [run["id"]]
    assert client.get("/workers").json() == [] and client.get("/workers/health").status_code == 503
    assert client.delete(f"/pipeline-runs/{run['id']}").status_code == 204
    assert client.delete(f"/pipelines/{pipeline['id']}").status_code == 204


def test_pipeline_graph_over_the_api(client):
    agent = {"system_prompt": "Fai.", "model": MODEL}
    body = _pipeline_body(name="Grafo", steps=[
        {"name": "Check", "kind": "agent", "input_template": "{input}", "agent": agent, "position_x": 40, "position_y": 80},
        {"name": "Pull", "kind": "agent", "input_template": "{input}", "agent": agent},
        {"name": "Avvisa", "kind": "agent", "input_template": "{input}", "agent": agent},
    ])
    body["edges"] = [
        {"source": "input", "target": "Check"},
        {"source": "Check", "target": "Pull", "condition": "contains", "value": "OK"},
        {"source": "Check", "target": "Avvisa", "condition": "otherwise"},
    ]

    created = client.post("/projects/acme/pipelines", json=body)

    assert created.status_code == 201, created.text
    pipeline = created.json()
    assert [(e["source"], e["target"], e["condition"]) for e in pipeline["edges"]] == [
        ("input", "Check", "always"), ("Check", "Pull", "contains"), ("Check", "Avvisa", "otherwise"),
    ]
    assert (pipeline["steps"][0]["position_x"], pipeline["steps"][0]["position_y"]) == (40, 80)
    broken = {**body, "name": "Rotto", "edges": body["edges"][:1]}
    assert client.post("/projects/acme/pipelines", json=broken).status_code == 400
    assert client.post("/projects/acme/pipelines", json={**body, "name": "X", "edges": [
        {"source": "input", "target": "Check", "condition": "boh"}]}).status_code == 422


def test_functions_describe_their_params(client):
    functions = {f["name"]: f for f in client.get("/functions").json()}

    [title] = functions["save_note"]["params"]
    assert (title["name"], title["type"], title["default"]) == ("title", "str", "Automation {date} {time}")
    assert [p["name"] for p in functions["git_status"]["params"]] == ["repository"]


# ---------------------------------------------------------------- atlassian

def test_atlassian_settings_never_return_the_token(client):
    assert client.get("/projects/acme/atlassian").json() is None
    body = {"base_url": "https://acme.atlassian.net", "email": "a@b.it", "api_token": "secret"}

    saved = client.put("/projects/acme/atlassian", json=body).json()

    assert saved["has_token"] and "secret" not in str(saved)
    kept = client.put("/projects/acme/atlassian", json={**body, "api_token": ""}).json()
    assert kept["has_token"]
    assert client.put("/projects/acme/atlassian", json={**body, "base_url": "x"}).status_code == 400
    assert client.delete("/projects/acme/atlassian").status_code == 204
    assert client.post("/projects/acme/atlassian/check").status_code == 400


class _FakeJira:
    def get_issue(self, key):
        return JiraIssue(key=key, summary="Login rotto", status="To Do", description="Non entra.",
                         url=f"https://acme.atlassian.net/browse/{key}")


class _FakeConfluence:
    def get_space(self, key):
        return ConfluenceSpace(id="7", key=key, name="Docs", url="https://acme.atlassian.net/wiki/spaces/DOC")

    def list_pages(self, space_id, limit):
        return [ConfluencePage(id="1", title="Setup", space_id=space_id, url="https://acme.atlassian.net/wiki/1")]

    def get_page(self, page_id):
        return ConfluencePage(id=page_id, title="Setup", url="https://acme.atlassian.net/wiki/1", body="Installa tutto.")

    def search_pages(self, text, space_key, limit):
        return [ConfluenceSearchHit(id="1", title="Setup", excerpt=f"...{text}...", url="https://acme.atlassian.net/wiki/1")]


def test_jira_and_confluence_reads(client, monkeypatch):
    site = AtlassianSite(_FakeJira(), _FakeConfluence(), confluence_space_key="DOC")
    monkeypatch.setattr(client.app.state.container.atlassian_service, "site", lambda project: site)

    issue = client.get("/projects/acme/atlassian/jira/issues/proj-12").json()
    assert (issue["key"], issue["summary"], issue["description"]) == ("PROJ-12", "Login rotto", "Non entra.")
    assert client.get("/projects/acme/atlassian/jira/issues/nope").status_code == 400

    assert [p["title"] for p in client.get("/projects/acme/atlassian/confluence/pages").json()] == ["Setup"]
    assert client.get("/projects/acme/atlassian/confluence/pages/1").json()["body"] == "Installa tutto."
    assert client.get("/projects/acme/atlassian/confluence/pages/abc").status_code == 400
    [hit] = client.get("/projects/acme/atlassian/confluence/search", params={"q": "install"}).json()
    assert hit["excerpt"] == "...install..."
    assert client.get("/projects/acme/atlassian/confluence/search", params={"q": " "}).status_code == 400


def test_an_issue_or_a_page_becomes_a_context_reference_linked_where_chosen(client, monkeypatch):
    site = AtlassianSite(_FakeJira(), _FakeConfluence())
    monkeypatch.setattr(client.app.state.container.atlassian_service, "site", lambda project: site)
    task = client.post("/projects/acme/agent-tasks", json={"title": "Fix"}).json()["name"]
    todo = client.post("/projects/acme/todo-lists", json={"title": "Giro"}).json()["name"]

    created = client.post("/projects/acme/atlassian/jira/issues/proj-12/reference", json={"link_to": [task, todo]})
    assert created.status_code == 201
    name = created.json()["name"]
    [reference] = client.get("/projects/acme/references").json()
    assert (reference["name"], reference["source"], reference["source_url"]) == (name, "jira", "https://acme.atlassian.net/browse/PROJ-12")
    assert reference["title"].startswith("PROJ-12") and "Stato: To Do" in reference["content"] and reference["content"].endswith("Non entra.")
    assert reference["linked_from"] == [task, todo]

    again = client.post("/projects/acme/atlassian/jira/issues/PROJ-12/reference", json={"link_to": [task]})
    assert again.status_code == 200 and again.json() == {"name": name, "created": False}  # refreshed, not duplicated
    assert client.get("/projects/acme/agent-tasks").json()[0]["references"] == [name]  # linked once

    page = client.post("/projects/acme/atlassian/confluence/pages/1/reference", json={}).json()
    assert page == {"name": "context-reference-setup.md", "created": True}
    client.put("/projects/acme/references/context-reference-setup.md", json={"title": "Setup", "source_url": "https://altrove"})
    assert client.post("/projects/acme/atlassian/confluence/pages/1/reference", json={}).status_code == 409  # another note took the name
    assert client.post("/projects/acme/atlassian/jira/issues/PROJ-12/reference", json={"link_to": ["appunti.md"]}).status_code == 400


def test_favorites(client):
    site = {"base_url": "https://acme.atlassian.net", "email": "a@b.it", "api_token": "t"}
    client.put("/projects/acme/atlassian", json=site)
    issue = {"kind": "jira_issue", "ref": "proj-3", "title": "Bug", "url": "https://acme.atlassian.net/browse/PROJ-3"}

    created = client.post("/projects/acme/atlassian/favorites", json=issue)
    page = client.post("/projects/acme/atlassian/favorites",
                       json={"kind": "confluence_page", "ref": "9", "title": "Setup"}).json()

    assert created.status_code == 201 and created.json()["ref"] == "PROJ-3"
    assert client.post("/projects/acme/atlassian/favorites", json=issue).json()["id"] == created.json()["id"]
    assert [f["kind"] for f in client.get("/projects/acme/atlassian/favorites").json()] == ["jira_issue", "confluence_page"]
    assert client.post("/projects/acme/atlassian/favorites", json={**issue, "kind": "nope"}).status_code == 422
    assert client.delete(f"/projects/acme/atlassian/favorites/{page['id']}").status_code == 204
    assert client.delete(f"/projects/acme/atlassian/favorites/{page['id']}").status_code == 404


def test_jira_without_atlassian_configured(client):
    response = client.get("/projects/acme/atlassian/jira/issues/PROJ-1")

    assert response.status_code == 400 and "Impostazioni" in response.json()["detail"]


# ------------------------------------------------------------------ masking

def test_masking_map(client):
    added = client.post("/projects/acme/masking", json={"category": "person", "value": "Mario Rossi"})

    assert added.status_code == 201 and added.json()["alias"] == "PERSONA_1"
    assert client.post("/projects/acme/masking", json={"value": "ab"}).status_code == 400
    assert [e["alias"] for e in client.get("/projects/acme/masking").json()] == ["PERSONA_1"]
    assert client.delete("/projects/acme/masking/PERSONA_1").status_code == 204
    assert client.delete("/projects/acme/masking/PERSONA_1").status_code == 404


# -------------------------------------------------------------------- admin

def test_config_is_masked(client):
    config = client.get("/admin/config").json()

    assert config["settings"]["openai_api_key"] != "test"
    assert config["redis_dashboard_port"] == 8083


def test_observability(client, run_store):
    run_store.save(make_run_record("run-1"))

    [run] = client.get("/observability/runs").json()
    assert (run["run_id"], run["total_tokens"]["input_tokens"]) == ("run-1", 150)
    assert client.get("/observability/runs/run-1/trace").json()["output"] == "Hello, Mario!"
    assert client.get("/observability/runs/missing/trace").status_code == 404
    assert client.get("/observability/tool-calls").json()[0]["tool_name"] == "hello_world"


class _FakeDump:
    def dump(self, user, database):
        return b"-- dump"


def test_backups(client, tmp_path):
    client.app.state.container.backup_service = BackupService(tmp_path, "postgresql://app@localhost/app", _FakeDump())
    assert client.get("/admin/backups").json()["backups"] == []

    created = client.post("/admin/backups")

    assert created.status_code == 201
    name = created.json()["name"]
    assert [b["name"] for b in client.get("/admin/backups").json()["backups"]] == [name]
    assert client.get(f"/admin/backups/{name}").content == b"-- dump"
    assert client.get("/admin/backups/nope.sql").status_code == 400


def test_model_catalog_marks_and_protects_models_in_use(client):
    catalog = client.get("/models").json()
    in_use = next(m for m in catalog if m["in_use"])  # the default agent's model

    assert client.put("/models", json=[m for m in catalog if m is not in_use]).status_code == 409
    toggled = [{**m, "active": False} if m is in_use else m for m in catalog]
    saved = client.put("/models", json=toggled).json()
    assert next(m for m in saved if m["model"] == in_use["model"])["active"] is False
