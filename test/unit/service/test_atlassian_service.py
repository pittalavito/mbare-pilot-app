import httpx
import pytest
from cryptography.fernet import Fernet

from core.error import NotFoundError, ValidationError
from core.secret_box import SecretBox
from domain.client.atlassian.client import AtlassianHttp, ConfluenceClient, JiraClient
from domain.store.db.store import DbAtlassianRepository
from models.domain.atlassian import FavoriteKind
from models.domain.project import Project, ProjectSource
from service.atlassian_service import AtlassianService, AtlassianSite


def _site(handler, **defaults) -> AtlassianSite:
    http = AtlassianHttp("https://acme.atlassian.net", "me@acme.com", "t", transport=httpx.MockTransport(handler))
    return AtlassianSite(JiraClient(http), ConfluenceClient(http), **defaults)


@pytest.fixture
def service(store_service):
    for name in ("Alpha", "Beta"):
        store_service.save_project(Project(name=name, source=ProjectSource.FOLDER, root_path=f"/tmp/{name}"))
    return AtlassianService(store_service)


def _save(service, project="Alpha", **overrides):
    values = dict(base_url="https://alpha.atlassian.net/", email="me@alpha.com", api_token="tok-a")
    values.update(overrides)
    return service.save_settings(project, **values)


# ------------------------------------------------------------ per-project settings

def test_not_configured_project_explains_where_to_set_it(service):
    assert service.is_configured("Alpha") is False
    with pytest.raises(ValidationError, match="Impostazioni"):
        service.site("Alpha")


def test_settings_are_per_project(service):
    _save(service, jira_project_key=" alp ", confluence_space_key="DOC")
    _save(service, "Beta", base_url="https://beta.atlassian.net", email="me@beta.com", api_token="tok-b")

    alpha, beta = service.get_settings("Alpha"), service.get_settings("Beta")
    assert alpha.base_url == "https://alpha.atlassian.net"
    assert alpha.jira_project_key == "ALP" and alpha.confluence_space_key == "DOC"
    assert beta.base_url == "https://beta.atlassian.net" and beta.jira_project_key == ""
    assert service.site("Alpha").jira_project_key == "ALP"
    assert service.site("Beta").jira_project_key is None


def test_token_is_stored_encrypted(service, engine):
    _save(service)

    row = DbAtlassianRepository(engine).get("Alpha")
    assert row.api_token != "tok-a" and "tok-a" not in row.api_token
    assert service.get_settings("Alpha").api_token.get_secret_value() == "tok-a"


def test_token_unreadable_with_another_key_means_not_configured(store_service, service, monkeypatch):
    _save(service)
    monkeypatch.setattr(store_service, "_secret_box", SecretBox(Fernet.generate_key().decode()))

    assert service.get_settings("Alpha").base_url == "https://alpha.atlassian.net"
    assert service.is_configured("Alpha") is False
    with pytest.raises(ValidationError, match="obbligatorio"):
        _save(service, api_token="")


def test_empty_token_keeps_the_saved_one(service):
    _save(service)
    _save(service, email="other@alpha.com", api_token="")

    settings = service.get_settings("Alpha")
    assert settings.email == "other@alpha.com"
    assert settings.api_token.get_secret_value() == "tok-a"


def test_site_is_rebuilt_when_settings_change(service):
    _save(service)
    first = service.site("Alpha")
    assert service.site("Alpha") is first

    _save(service, jira_project_key="NEW")
    assert service.site("Alpha") is not first


@pytest.mark.parametrize("overrides", [
    dict(base_url="acme.atlassian.net"),
    dict(base_url="http://acme.atlassian.net"),
    dict(email=" "),
    dict(api_token=""),
    dict(jira_project_key='AL" OR 1=1'),
    dict(confluence_space_key="a b"),
])
def test_invalid_settings_rejected(service, overrides):
    with pytest.raises(ValidationError):
        _save(service, **overrides)
    assert service.get_settings("Alpha") is None


def test_unknown_project_rejected(service):
    with pytest.raises(NotFoundError):
        _save(service, "Nope")


def test_remove_settings(service):
    _save(service)
    assert service.remove_settings("Alpha") is True
    assert service.is_configured("Alpha") is False


# -------------------------------------------------------------------- site calls

def test_project_issues_builds_jql_from_a_valid_key():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["jql"] = request.url.params["jql"]
        return httpx.Response(200, json={"issues": [], "isLast": True})

    _site(handler).project_issues(" alpha ", open_only=True)

    assert seen["jql"] == 'project = "ALPHA" AND statusCategory != Done ORDER BY updated DESC'


def test_project_issues_defaults_to_the_projects_jira_key():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["jql"] = request.url.params["jql"]
        return httpx.Response(200, json={"issues": [], "isLast": True})

    _site(handler, jira_project_key="ALP").project_issues()

    assert seen["jql"] == 'project = "ALP" ORDER BY updated DESC'


def test_without_key_nor_default_rejected():
    def handler(request):
        raise AssertionError("no request expected")

    with pytest.raises(ValidationError, match="predefinito"):
        _site(handler).project_issues()
    with pytest.raises(ValidationError, match="predefinito"):
        _site(handler).list_space_pages()


@pytest.mark.parametrize("key", ["1ABC", 'AL" OR 1=1', "toolongprojectkey"])
def test_project_issues_rejects_invalid_keys_before_any_request(key):
    def handler(request):
        raise AssertionError("no request expected")

    with pytest.raises(ValidationError):
        _site(handler).project_issues(key)


@pytest.mark.parametrize("key", ["ALPHA", "alpha-x", "../1"])
def test_get_issue_rejects_invalid_keys(key):
    with pytest.raises(ValidationError):
        _site(lambda request: httpx.Response(200, json={})).get_issue(key)


def test_list_space_pages_resolves_key_to_id():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/wiki/api/v2/spaces":
            assert request.url.params["keys"] == "DOC"
            return httpx.Response(200, json={"results": [{"id": 77, "key": "DOC", "name": "Docs"}]})
        assert request.url.path == "/wiki/api/v2/spaces/77/pages"
        return httpx.Response(200, json={"results": [{"id": 1, "title": "Home"}]})

    assert [p.title for p in _site(handler).list_space_pages("DOC")] == ["Home"]
    assert [p.title for p in _site(handler, confluence_space_key="DOC").list_space_pages()] == ["Home"]


def test_list_space_pages_unknown_space():
    with pytest.raises(NotFoundError):
        _site(lambda request: httpx.Response(200, json={"results": []})).list_space_pages("NOPE")


@pytest.mark.parametrize("call", [
    lambda s: s.search_issues("  "),
    lambda s: s.search_pages(""),
    lambda s: s.get_page("abc"),
])
def test_empty_or_invalid_inputs_rejected(call):
    with pytest.raises(ValidationError):
        call(_site(lambda request: httpx.Response(200, json={})))


# ---------------------------------------------------------------- favorites

def test_favorites_per_project_without_duplicates(service, store_service):
    issue = service.add_favorite("Alpha", FavoriteKind.JIRA_ISSUE, " proj-1 ", "Login rotto", "https://x/browse/PROJ-1")
    page = service.add_favorite("Alpha", FavoriteKind.CONFLUENCE_PAGE, "42", "Setup", "https://x/wiki/42")
    again = service.add_favorite("Alpha", FavoriteKind.JIRA_ISSUE, "PROJ-1", "Altro titolo", "")

    assert issue.ref == "PROJ-1" and again.id == issue.id and again.title == "Login rotto"
    assert [(f.kind, f.ref) for f in service.list_favorites("Alpha")] == [
        (FavoriteKind.JIRA_ISSUE, "PROJ-1"), (FavoriteKind.CONFLUENCE_PAGE, "42"),
    ]
    with pytest.raises(NotFoundError):
        service.remove_favorite("Beta", page.id)  # another project's favorite
    service.remove_favorite("Alpha", page.id)
    assert [f.ref for f in service.list_favorites("Alpha")] == ["PROJ-1"]
    with pytest.raises(ValidationError):
        service.add_favorite("Alpha", FavoriteKind.JIRA_ISSUE, " ", "x", "")

