"""A project's Atlassian site, typed: settings (the token is write-only),
read-only Jira issues and Confluence pages, favorites."""
from api_client.http import ApiClient, segment
from api_client.models import AtlassianSettings, AtlassianUser, ConfluencePage, ConfluenceSearchHit, Favorite, JiraIssue


class AtlassianApi:

    def __init__(self, client: ApiClient):
        self._client = client

    def settings(self, project: str) -> AtlassianSettings | None:
        """None = not configured."""
        data = self._client.get(_base(project))
        return AtlassianSettings.model_validate(data) if data else None

    def save(self, project: str, body: dict) -> AtlassianSettings:
        """``body``: base_url, email, api_token (empty = keep), jira_project_key, confluence_space_key."""
        return AtlassianSettings.model_validate(self._client.put(_base(project), json=body))

    def remove(self, project: str) -> None:
        self._client.delete(_base(project))

    def check(self, project: str) -> AtlassianUser:
        return AtlassianUser.model_validate(self._client.post(f"{_base(project)}/check"))

    def issue(self, project: str, key: str) -> JiraIssue:
        return JiraIssue.model_validate(self._client.get(f"{_base(project)}/jira/issues/{segment(key.strip())}"))

    def pages(self, project: str) -> list[ConfluencePage]:
        """Pages of the project's Confluence space, without their body."""
        return [ConfluencePage.model_validate(item) for item in self._client.get(f"{_base(project)}/confluence/pages")]

    def page(self, project: str, page_id: str) -> ConfluencePage:
        return ConfluencePage.model_validate(self._client.get(f"{_base(project)}/confluence/pages/{segment(page_id)}"))

    def search_pages(self, project: str, text: str) -> list[ConfluenceSearchHit]:
        hits = self._client.get(f"{_base(project)}/confluence/search", params={"q": text})
        return [ConfluenceSearchHit.model_validate(item) for item in hits]

    def favorites(self, project: str) -> list[Favorite]:
        """Saved in the app: no call to Atlassian."""
        return [Favorite.model_validate(item) for item in self._client.get(f"{_base(project)}/favorites")]

    def add_favorite(self, project: str, kind: str, ref: str, title: str, url: str) -> Favorite:
        body = {"kind": kind, "ref": ref, "title": title, "url": url}
        return Favorite.model_validate(self._client.post(f"{_base(project)}/favorites", json=body))

    def remove_favorite(self, project: str, favorite_id: int) -> None:
        self._client.delete(f"{_base(project)}/favorites/{favorite_id}")


def _base(project: str) -> str:
    return f"/projects/{segment(project)}/atlassian"
