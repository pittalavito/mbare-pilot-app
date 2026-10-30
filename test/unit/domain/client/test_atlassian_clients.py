"""Jira/Confluence clients against a fake Atlassian site (httpx.MockTransport)."""
import base64

import httpx
import pytest

from core.error import NotFoundError, UpstreamError, ValidationError
from domain.client.atlassian.client import AtlassianHttp, ConfluenceClient, JiraClient
from domain.client.atlassian.confluence import storage_to_text
from domain.client.atlassian.jira import adf_to_text

BASE = "https://acme.atlassian.net"


def _http(handler) -> AtlassianHttp:
    return AtlassianHttp(BASE, "me@acme.com", "secret-token", transport=httpx.MockTransport(handler))


# ------------------------------------------------------------------- HTTP

def test_requests_use_basic_auth():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["Authorization"]
        return httpx.Response(200, json={"accountId": "1", "displayName": "Me", "emailAddress": "me@acme.com"})

    user = JiraClient(_http(handler)).myself()

    assert user.display_name == "Me"
    assert seen["auth"] == "Basic " + base64.b64encode(b"me@acme.com:secret-token").decode()


@pytest.mark.parametrize("status, error", [
    (401, ValidationError), (403, ValidationError), (404, NotFoundError),
    (400, ValidationError), (429, UpstreamError), (500, UpstreamError),
])
def test_http_errors_are_mapped(status, error):
    def handler(request):
        return httpx.Response(status, json={"errorMessages": ["boom"]}, headers={"Retry-After": "3"})
    with pytest.raises(error):
        JiraClient(_http(handler)).myself()


def test_network_error_is_upstream():
    def handler(request):
        raise httpx.ConnectError("down")

    with pytest.raises(UpstreamError):
        JiraClient(_http(handler)).myself()


# ------------------------------------------------------------------- Jira

def test_list_projects_follows_offset_pagination():
    pages = {
        0: {"values": [{"id": "1", "key": "ALPHA", "name": "Alpha"}], "isLast": False},
        1: {"values": [{"id": "2", "key": "BETA", "name": "Beta", "projectTypeKey": "software"}], "isLast": True},
    }
    def handler(request):
        return httpx.Response(200, json=pages[int(request.url.params["startAt"])])

    projects = JiraClient(_http(handler)).list_projects()

    assert [p.key for p in projects] == ["ALPHA", "BETA"]
    assert projects[1].url == f"{BASE}/browse/BETA" and projects[1].project_type == "software"


def test_search_issues_follows_next_page_token_and_maps_fields():
    issue = {
        "key": "ALPHA-1",
        "fields": {
            "summary": "Login rotto",
            "status": {"name": "To Do"},
            "issuetype": {"name": "Bug"},
            "priority": {"name": "High"},
            "assignee": {"displayName": "Mario"},
            "updated": "2026-10-01T10:00:00.000+0200",
            "description": {"type": "doc", "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Non riesco ad entrare."}]},
            ]},
        },
    }
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/rest/api/3/search/jql"
        calls.append(request.url.params.get("nextPageToken"))
        if len(calls) == 1:
            return httpx.Response(200, json={"issues": [issue], "nextPageToken": "t2", "isLast": False})
        return httpx.Response(200, json={"issues": [{**issue, "key": "ALPHA-2"}], "isLast": True})

    issues = JiraClient(_http(handler)).search_issues("project = ALPHA")

    assert calls == [None, "t2"]
    assert [i.key for i in issues] == ["ALPHA-1", "ALPHA-2"]
    first = issues[0]
    assert (first.status, first.issue_type, first.priority, first.assignee) == ("To Do", "Bug", "High", "Mario")
    assert first.description == "Non riesco ad entrare."
    assert first.updated.isoformat() == "2026-10-01T10:00:00+02:00"


def test_search_issues_respects_limit():
    def handler(request):
        return httpx.Response(200, json={
            "issues": [{"key": f"A-{n}", "fields": {}} for n in range(int(request.url.params["maxResults"]))],
            "nextPageToken": "more", "isLast": False,
        })

    assert len(JiraClient(_http(handler)).search_issues("x", limit=3)) == 3


def test_adf_to_text_handles_lists_breaks_and_mentions():
    doc = {"type": "doc", "content": [
        {"type": "heading", "content": [{"type": "text", "text": "Titolo"}]},
        {"type": "bulletList", "content": [
            {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "uno"}]}]},
            {"type": "listItem", "content": [{"type": "paragraph", "content": [
                {"type": "mention", "attrs": {"text": "@Mario"}}, {"type": "hardBreak"}, {"type": "text", "text": "due"},
            ]}]},
        ]},
    ]}

    assert adf_to_text(doc) == "Titolo\n- uno\n- @Mario\ndue"
    assert adf_to_text(None) == ""


# ------------------------------------------------------------- Confluence

def test_list_spaces_follows_cursor_links():
    def handler(request: httpx.Request) -> httpx.Response:
        if "cursor" not in request.url.params:
            return httpx.Response(200, json={
                "results": [{"id": 1, "key": "DOC", "name": "Docs", "_links": {"webui": "/spaces/DOC"}}],
                "_links": {"next": "/wiki/api/v2/spaces?cursor=abc&limit=50"},
            })
        return httpx.Response(200, json={"results": [{"id": 2, "key": "ENG", "name": "Engineering"}], "_links": {}})

    spaces = ConfluenceClient(_http(handler)).list_spaces()

    assert [s.key for s in spaces] == ["DOC", "ENG"]
    assert spaces[0].url == f"{BASE}/wiki/spaces/DOC"


def test_get_page_returns_plain_text_body():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["body-format"] == "storage"
        return httpx.Response(200, json={
            "id": "42", "title": "Setup", "spaceId": 7,
            "body": {"storage": {"value": "<h1>Setup</h1><p>Installa <strong>uv</strong>.</p><ul><li>uno</li><li>due</li></ul>"}},
            "_links": {"webui": "/spaces/DOC/pages/42"},
        })

    page = ConfluenceClient(_http(handler)).get_page("42")

    assert page.body == "Setup\nInstalla uv.\n- uno\n- due"
    assert page.space_id == "7" and page.url == f"{BASE}/wiki/spaces/DOC/pages/42"


def test_search_pages_builds_escaped_cql():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["cql"] = request.url.params["cql"]
        return httpx.Response(200, json={"results": [
            {"content": {"id": "9", "title": "FAQ"}, "excerpt": "una <b>risposta</b>", "url": "/spaces/DOC/pages/9"},
        ]})

    hits = ConfluenceClient(_http(handler)).search_pages('come "fare"', space_key="DOC")

    assert seen["cql"] == 'type = page AND text ~ "come \\"fare\\"" AND space = "DOC"'
    assert hits[0].title == "FAQ" and hits[0].excerpt == "una risposta"


def test_storage_to_text_empty():
    assert storage_to_text("") == ""
