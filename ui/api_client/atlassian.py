"""A project's Atlassian settings, typed. The token is write-only."""
from api_client.http import ApiClient, segment
from api_client.models import AtlassianSettings, AtlassianUser


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


def _base(project: str) -> str:
    return f"/projects/{segment(project)}/atlassian"
