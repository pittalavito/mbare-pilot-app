"""Blocco 10: a Confluence or Jira task's draft published with the project's
Atlassian site (a fake one: httpx.MockTransport), through the API, and the
Markdown → storage / ADF conversion."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.container import Container
from domain.atlassian.publish_format import split_title, to_adf, to_storage
from domain.client.atlassian.confluence import ConfluenceClient
from domain.client.atlassian.http import AtlassianHttp
from domain.client.atlassian.jira import JiraClient
from models.domain.masking import MaskCategory
from models.domain.note import NoteType, Reference
from models.domain.project import Project, ProjectSource
from service.atlassian_service import AtlassianSite

BASE = "https://acme.atlassian.net"
DRAFT = "# Bozza: Guida al login\n\n## Contesto\nIl servizio **REPO_X** gestisce il login.\n\n- passo uno\n- passo due\n"


class FakeAtlassian:
    """Just enough of Confluence v2 and Jira v3; ``forbidden`` answers 403 to every write."""

    def __init__(self):
        self.calls: list[tuple[str, str, dict | None]] = []
        self.forbidden = False
        self.page = {"id": "101", "title": "Login", "spaceId": "9", "version": {"number": 3}, "_links": {"webui": "/spaces/DOC/pages/101/Login"},
                     "body": {"storage": {"value": "<p>Vecchio testo</p>"}}}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        path = request.url.path
        self.calls.append((request.method, path, body))
        if request.method in ("POST", "PUT") and self.forbidden:
            return httpx.Response(403, json={"message": "non puoi scrivere"})
        if path == "/wiki/api/v2/spaces":
            return httpx.Response(200, json={"results": [{"id": "9", "key": "DOC", "name": "Doc", "_links": {"webui": "/spaces/DOC"}}]})
        if path == "/wiki/api/v2/pages" and request.method == "POST":
            return httpx.Response(200, json={"id": "202", "title": body["title"], "spaceId": "9", "_links": {"webui": "/spaces/DOC/pages/202/x"},
                                             "body": {"storage": {"value": body["body"]["value"]}}})
        if path in ("/wiki/api/v2/pages/101", "/wiki/api/v2/pages/202"):
            if request.method == "PUT":
                return httpx.Response(200, json={**self.page, "title": body["title"], "version": body["version"]})
            return httpx.Response(200, json={**self.page, "id": path.rsplit("/", 1)[-1]})
        if path == "/rest/api/3/issue" and request.method == "POST":
            return httpx.Response(201, json={"key": "NAV-8"})
        if path.startswith("/rest/api/3/issue/NAV-"):
            if request.method == "PUT":
                return httpx.Response(204)
            key = path.rsplit("/", 1)[-1]
            return httpx.Response(200, json={"key": key, "fields": {"summary": "Login lento", "description": {
                "type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Ci mette 10 s."}]}]}}})
        if path == "/rest/api/3/issue/createmeta/NAV/issuetypes":
            return httpx.Response(200, json={"issueTypes": [{"name": "Story"}, {"name": "Sub-task", "subtask": True}]})
        return httpx.Response(404, json={"message": f"non previsto: {path}"})


@pytest.fixture
def app(stores, project_store, tmp_path, monkeypatch):
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path=str(tmp_path)))
    fake = FakeAtlassian()
    http = AtlassianHttp(BASE, "me@acme.com", "t", transport=httpx.MockTransport(fake))
    site = AtlassianSite(JiraClient(http), ConfluenceClient(http), jira_project_key="NAV", confluence_space_key="DOC")
    with TestClient(create_app(Container(stores=stores))) as client:
        container = client.app.state.container
        monkeypatch.setattr(container.atlassian_service, "site", lambda project: site)
        yield client, container, fake


def _task(client, container, kind, title="Guida al login", references=()):
    task = client.post("/projects/acme/agent-tasks", json={"title": title, "type": kind, "status": "in_progress",
                                                          "references": list(references)}).json()["name"]
    alias = container.masking_service.add_term("acme", MaskCategory.REPOSITORY, "login-api").alias
    draft = f"bozza-{task.removeprefix('agent-task-')}"
    container.project_data_service.save_note("acme", draft, DRAFT.replace("REPO_X", alias))
    return task, alias


def test_a_new_confluence_page(app):
    client, container, fake = app
    task, alias = _task(client, container, "confluence")

    preview = client.get(f"/projects/acme/agent-tasks/{task}/publish").json()
    assert (preview["kind"], preview["mode"], preview["title"], preview["space_key"]) == ("confluence", "create", "Guida al login", "DOC")
    assert "**login-api**" in preview["body"] and preview["unmasked"] == [f"{alias} → login-api"]
    assert not [call for call in fake.calls if call[0] != "GET"]  # the preview writes nothing

    result = client.post(f"/projects/acme/agent-tasks/{task}/publish", json={"parent_id": "55"}).json()

    created = next(body for method, path, body in fake.calls if method == "POST")
    assert created["spaceId"] == "9" and created["parentId"] == "55" and created["title"] == "Guida al login"
    assert "<strong>login-api</strong>" in created["body"]["value"] and "<li>passo uno</li>" in created["body"]["value"]
    assert result["url"] == f"{BASE}/wiki/spaces/DOC/pages/202/x" and result["mode"] == "create"
    saved = client.get("/projects/acme/agent-tasks").json()[0]
    assert saved["status"] == "done" and result["reference"] in saved["references"]


def test_the_linked_page_is_updated_with_a_new_version(app):
    client, container, fake = app
    reference = container.project_data_service.create_reference("acme", NoteType.CONTEXT_REFERENCE, Reference(
        title="Login", source="confluence", source_url=f"{BASE}/wiki/spaces/DOC/pages/101/Login"))
    task, _ = _task(client, container, "confluence", references=[reference])

    preview = client.get(f"/projects/acme/agent-tasks/{task}/publish").json()
    assert (preview["mode"], preview["reference"], preview["target_body"]) == ("update", reference, "Vecchio testo")

    client.post(f"/projects/acme/agent-tasks/{task}/publish", json={})

    [(_, _, updated)] = [call for call in fake.calls if call[0] == "PUT"]
    assert updated["version"]["number"] == 4 and updated["title"] == "Guida al login"
    assert "login-api" in container.project_data_service.reference("acme", reference)[1].content


def test_jira_new_issue_and_linked_issue(app):
    client, container, fake = app
    assert client.get("/projects/acme/atlassian/jira/issue-types").json() == ["Story"]
    task, _ = _task(client, container, "jira", title="Storia login")

    assert client.get(f"/projects/acme/agent-tasks/{task}/publish").json()["project_key"] == "NAV"
    result = client.post(f"/projects/acme/agent-tasks/{task}/publish", json={"issue_type": "Story"}).json()
    created = next(body for method, path, body in fake.calls if method == "POST")
    assert created["fields"]["project"] == {"key": "NAV"} and created["fields"]["summary"] == "Guida al login"
    assert created["fields"]["description"]["type"] == "doc"
    assert result["url"] == f"{BASE}/browse/NAV-8"

    reference = result["reference"]  # the new issue, copied and linked: publishing again updates it
    fake.calls.clear()
    preview = client.get(f"/projects/acme/agent-tasks/{task}/publish").json()
    assert (preview["mode"], preview["reference"], preview["title"], preview["target_body"]) == ("update", reference, "Login lento", "Ci mette 10 s.")
    client.post(f"/projects/acme/agent-tasks/{task}/publish", json={})
    [(_, path, updated)] = [call for call in fake.calls if call[0] == "PUT"]
    assert path == "/rest/api/3/issue/NAV-8" and list(updated["fields"]) == ["description"]


def test_what_cannot_be_published(app):
    client, container, fake = app
    development = client.post("/projects/acme/agent-tasks", json={"title": "Codice"}).json()["name"]
    assert client.get(f"/projects/acme/agent-tasks/{development}/publish").status_code == 400
    no_draft = client.post("/projects/acme/agent-tasks", json={"title": "Senza bozza", "type": "jira"}).json()["name"]
    response = client.get(f"/projects/acme/agent-tasks/{no_draft}/publish")
    assert response.status_code == 404 and "salva prima" in response.json()["detail"]
    empty = client.post("/projects/acme/agent-tasks", json={"title": "Vuota", "type": "jira"}).json()["name"]
    container.project_data_service.save_note("acme", "bozza-vuota", "# Bozza: Vuota\n")
    assert client.get(f"/projects/acme/agent-tasks/{empty}/publish").status_code == 400

    task, _ = _task(client, container, "jira", title="Storia")
    fake.forbidden = True
    response = client.post(f"/projects/acme/agent-tasks/{task}/publish", json={"issue_type": "Story"})
    assert response.status_code == 400 and "permessi (403)" in response.json()["detail"]
    assert container.project_data_service.agent_task("acme", task).status.value == "in_progress"  # not done: nothing was published
    assert client.post(f"/projects/acme/agent-tasks/{task}/publish", json={}).status_code == 400  # a new issue needs its type


# ------------------------------------------------------------------- format

def test_markdown_to_storage_and_adf():
    markdown = ("## Contesto\nTesto **forte**, *corsivo*, `x<y` e [link](https://a.b).\nseguito\n\n- [x] uno\n- due\n\n1. a\n2. b\n\n"
                "```python\nprint(']]>')\n```\n\n| A | B |\n|---|---|\n| 1 | 2 \\| 3 |\n\n> nota\n\n---\n")
    storage = to_storage(markdown)
    assert storage.startswith("<h2>Contesto</h2><p>Testo <strong>forte</strong>, <em>corsivo</em>, <code>x&lt;y</code> e "
                              '<a href="https://a.b">link</a>. seguito</p><ul><li>uno</li><li>due</li></ul><ol><li>a</li><li>b</li></ol>')
    assert '<ac:parameter ac:name="language">python</ac:parameter>' in storage and "]]]]><![CDATA[>" in storage
    assert "<th>A</th>" in storage and "<td>2 | 3</td>" in storage and "<blockquote><p>nota</p></blockquote><hr />" in storage

    adf = to_adf(markdown)
    kinds = [node["type"] for node in adf["content"]]
    assert kinds == ["heading", "paragraph", "bulletList", "orderedList", "codeBlock", "table", "blockquote", "rule"]
    marks = [node.get("marks", [{}])[0].get("type") for node in adf["content"][1]["content"]]
    assert marks == [None, "strong", None, "em", None, "code", None, "link", None]
    assert to_adf("```\n```")["content"] == [{"type": "codeBlock", "content": []}]
    assert split_title("# Titolo\n\ncorpo", "x") == ("Titolo", "corpo")
    assert split_title("## Non è un titolo\ncorpo", "x") == ("x", "## Non è un titolo\ncorpo")
