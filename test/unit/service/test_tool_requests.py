"""The Architetto asks for a missing tool (request_tool) and the request,
of the whole app, reaches Claude Code through its own MCP server (/mcp-dev, a
token generated in Admin), which marks it working, done or dismissed."""
import httpx
import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.container import Container
from core.error import NotFoundError, ValidationError
from models.domain.agent import RunOrigin
from models.domain.pipeline import Pipeline, PipelineStep, StepKind
from models.domain.project import Project, ProjectSource
from models.domain.tool_request import ToolRequestStatus
from service.tool_request_service import ToolRequestService
from tool.context import ToolContext
from tool.registry import TOOL_REGISTRY
from unit.service.test_copilot_mcp import (  # noqa: F401
    engine,
    project,
    server,  # noqa: F401 (fixture: the API on a free port)
)


@pytest.fixture
def service(stores):
    return ToolRequestService(stores.tool_requests, stores.pipelines)


def test_requests_are_written_listed_and_moved_on(service, stores, project_store, tmp_path):
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path=str(tmp_path)))
    step = PipelineStep(name="Stato", kind=StepKind.TOOL, tool_name="git_status", params={"repository": "*"})
    stores.pipelines.save_pipeline(Pipeline(project_name="acme", name="Rilascio", steps=[step], edges=[]))
    with pytest.raises(ValidationError, match="titolo"):
        service.create("acme", " ", "", [])
    first = service.create("acme", " Tool git_tag ", " Crea un tag. ", ["il tag c'è", " "], automation="Rilascio")
    second = service.create("acme", "Tool jira_comment", "Commenta.", [])

    assert (first.title, first.objective, first.criteria, first.status) == ("Tool git_tag", "Crea un tag.", ["il tag c'è"], ToolRequestStatus.OPEN)
    assert [item.id for item in service.list_requests()] == [second.id, first.id]
    assert "git_status" in service.automation_yaml(first) and service.automation_yaml(second) == ""
    assert service.automation_yaml(first.model_copy(update={"automation": "Sparita"})) == ""

    with pytest.raises(ValidationError, match="PR"):
        service.update(first.id, ToolRequestStatus.DONE)
    with pytest.raises(ValidationError, match="perché"):
        service.update(second.id, ToolRequestStatus.DISMISSED)
    service.update(first.id, ToolRequestStatus.WORKING)
    done = service.update(first.id, ToolRequestStatus.DONE, pr_url=" https://github.com/x/y/pull/1 ")
    assert done.pr_url == "https://github.com/x/y/pull/1"
    service.update(second.id, ToolRequestStatus.DISMISSED, reason="c'è già jira_update")
    assert service.list_requests(only_open=True) == []
    with pytest.raises(NotFoundError):
        service.get(999)


def test_the_token_is_kept_only_as_its_hash(service, stores):
    assert not service.has_token()
    with pytest.raises(ValidationError, match="Token non valido"):
        service.check_token("qualcosa")
    token = service.new_token()
    assert service.has_token() and stores.tool_requests.token_hash() != token
    service.check_token(token)
    newer = service.new_token()
    with pytest.raises(ValidationError):
        service.check_token(token)  # the old one stops working
    service.check_token(newer)
    with pytest.raises(ValidationError):
        service.check_token("")


def test_the_architetto_asks_for_a_tool_only_in_a_chat(service, stores, project_store, git_service, tmp_path):
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path=str(tmp_path)))
    spec = TOOL_REGISTRY["request_tool"]
    chat = ToolContext(project_name="acme", git=git_service, origin=RunOrigin.CHAT, tool_requests=service)

    answer = spec.build(chat).func(title="Tool git_tag", objective="Crea un tag.", criteria=["c'è"], automation="Rilascio")

    assert answer.request > 0 and answer.link == f"/admin?tab=tool-requests&request={answer.request}"
    [request] = service.list_requests()
    assert (request.project_name, request.automation) == ("acme", "Rilascio")
    assert stores.projects.get("acme") is not None and spec.chatbot_only
    assert "Serve un titolo" in spec.build(chat).func(title=" ", objective="", criteria=[]).error
    outside = ToolContext(project_name="acme", git=git_service, origin=RunOrigin.PIPELINE, tool_requests=service)
    assert spec.build(outside).func(title="x", objective="", criteria=[]).error


def _call(base, token, name, arguments=None, method="tools/call"):
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": {"name": name, "arguments": arguments or {}}}
    headers = {"Accept": "application/json, text/event-stream", "Authorization": f"Bearer {token}"}
    return httpx.post(f"{base}/mcp-dev/", json=body, headers=headers, timeout=10).json()["result"]


def test_claude_code_works_the_requests_through_its_mcp_server(server):  # noqa: F811
    container, base = server
    service = container.tool_request_service
    request = service.create("acme", "Tool git_tag", "Crea un tag.", ["c'è"])
    wrong = _call(base, "sbagliato", "list_tool_requests")
    assert wrong["isError"] and "Token non valido" in wrong["content"][0]["text"]
    token = service.new_token()

    listed = _call(base, token, "list_tool_requests")["structuredContent"]["result"]
    assert [item["title"] for item in listed] == ["Tool git_tag"]
    read = _call(base, token, "read_tool_request", {"request": request.id})["structuredContent"]
    assert (read["objective"], read["automation_yaml"]) == ("Crea un tag.", "")
    _call(base, token, "update_tool_request", {"request": request.id, "status": "working"})
    done = _call(base, token, "update_tool_request", {"request": request.id, "status": "done", "pr_url": "https://github.com/x/y/pull/7"})
    assert done["structuredContent"]["status"] == "done"
    assert _call(base, token, "list_tool_requests")["structuredContent"]["result"] == []
    missing = _call(base, token, "read_tool_request", {"request": 999})
    assert missing["isError"]
    tools = httpx.post(f"{base}/mcp-dev/", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                       headers={"Accept": "application/json, text/event-stream"}, timeout=10).json()["result"]["tools"]
    assert sorted(tool["name"] for tool in tools) == ["list_tool_requests", "read_tool_request", "update_tool_request"]


def test_the_admin_api(stores, project_store, tmp_path, config):
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path=str(tmp_path)))
    container = Container(stores=stores)
    request = container.tool_request_service.create("acme", "Tool git_tag", "Crea un tag.", [])
    with TestClient(create_app(container)) as client:
        state = client.get("/admin/tool-requests").json()
        assert state["has_token"] is False and [item["id"] for item in state["requests"]] == [request.id]
        created = client.post("/admin/tool-requests/token").json()
        assert created["token"] and created["url"].endswith("/mcp-dev/") and created["token"] in created["command"]
        assert client.get("/admin/tool-requests").json()["has_token"] is True
        assert client.post(f"/admin/tool-requests/{request.id}/dismiss", json={"reason": ""}).status_code == 400
        assert client.post(f"/admin/tool-requests/{request.id}/dismiss", json={"reason": "non serve"}).json()["status"] == "dismissed"
        assert client.post("/admin/tool-requests/999/dismiss", json={"reason": "x"}).status_code == 404
