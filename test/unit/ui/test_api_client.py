"""The UI's API client: error mapping, and the projects contract end-to-end
against the real FastAPI app (in-memory store)."""
import httpx
import pytest
from fastapi.testclient import TestClient

from api_client.http import ApiClient, ApiError, ApiUnavailable
from api_client.projects import ProjectsApi
from core.app import create_app
from core.container import Container
from domain.project.folder_browser import FolderBrowser
from service.project_service import ProjectService


# ---------------------------------------------------------------- errors

def _client(handler) -> ApiClient:
    return ApiClient("http://api.test", transport=httpx.MockTransport(handler))


def test_app_error_detail_is_the_message():
    client = _client(lambda request: httpx.Response(409, json={"detail": "Esiste già"}))

    with pytest.raises(ApiError) as exc:
        client.get("/x")
    assert (exc.value.status, str(exc.value)) == (409, "Esiste già")


def test_validation_errors_are_joined():
    detail = [{"loc": ["body", "name"], "msg": "Field required"}, {"loc": ["body", "parent"], "msg": "Field required"}]
    client = _client(lambda request: httpx.Response(422, json={"detail": detail}))

    with pytest.raises(ApiError, match="name: Field required; parent: Field required"):
        client.post("/x", json={})


def test_unreachable_api_explains_how_to_start_it():
    def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(ApiUnavailable, match="pannello Backend"):
        _client(handler).get("/health")


def test_empty_body_is_none():
    assert _client(lambda request: httpx.Response(204)).delete("/x") is None


# -------------------------------------------------------------- contract

@pytest.fixture
def projects(store_service, tmp_path):
    root = tmp_path / "workspace"
    (root / "existing app").mkdir(parents=True)
    container = Container(store_service=store_service)
    container.project_service = ProjectService(store_service, FolderBrowser([root]))
    with TestClient(create_app(container)) as test_client:
        client = ApiClient("http://testserver")
        client._client = test_client  # TestClient is an httpx.Client bound to the app
        yield ProjectsApi(client), root


def test_projects_contract_end_to_end(projects):
    api, root = projects

    listing = api.list_folder()
    assert [f.name for f in listing.subfolders] == ["existing app"]

    created = api.open_folder(listing.subfolders[0].path, name="Con spazi e accentò")
    assert created.folder_exists and created.source == "folder"
    assert api.get("Con spazi e accentò").name == "Con spazi e accentò"

    updated = api.update("Con spazi e accentò", "desc", api.embedding_models()[0])
    assert updated.description == "desc"

    scratch = api.create_from_scratch("Nuovo", str(root))
    assert scratch.source == "scratch" and (root / "Nuovo").is_dir()
    assert {p.name for p in api.all()} == {"Con spazi e accentò", "Nuovo"}

    api.remove("Nuovo")
    with pytest.raises(ApiError) as exc:
        api.get("Nuovo")
    assert exc.value.status == 404
