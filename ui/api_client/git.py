"""Git endpoints of a project, typed (read-only)."""
from api_client.http import ApiClient, segment
from api_client.models import Commit, GitStatus, Repository


class GitApi:

    def __init__(self, client: ApiClient):
        self._client = client

    def repositories(self, project: str) -> list[Repository]:
        return [Repository.model_validate(item) for item in self._client.get(f"{_base(project)}/repositories")]

    def log(self, project: str, path: str, limit: int = 50, *, author: str = "", message: str = "",
            commit: str = "") -> list[Commit]:
        params = {"path": path, "limit": limit, "author": author, "message": message, "commit": commit}
        return [Commit.model_validate(item) for item in self._client.get(f"{_base(project)}/log", params=params)]

    def status(self, project: str, path: str) -> GitStatus:
        return GitStatus.model_validate(self._client.get(f"{_base(project)}/status", params={"path": path}))


def _base(project: str) -> str:
    return f"/projects/{segment(project)}/git"
