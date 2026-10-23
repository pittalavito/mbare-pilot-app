"""A project's masking map, typed."""
from api_client.http import ApiClient, segment
from api_client.models import MaskEntry


class MaskingApi:

    def __init__(self, client: ApiClient):
        self._client = client

    def entries(self, project: str) -> list[MaskEntry]:
        return [MaskEntry.model_validate(item) for item in self._client.get(_base(project))]

    def add(self, project: str, category: str, value: str) -> MaskEntry:
        return MaskEntry.model_validate(self._client.post(_base(project), json={"category": category, "value": value}))

    def remove(self, project: str, alias: str) -> None:
        self._client.delete(f"{_base(project)}/{segment(alias)}")


def _base(project: str) -> str:
    return f"/projects/{segment(project)}/masking"
