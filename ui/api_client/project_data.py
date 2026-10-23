"""A project's data endpoints, typed: notes and uploaded files."""
from api_client.http import ApiClient, segment
from api_client.models import DataFile


class ProjectDataApi:

    def __init__(self, client: ApiClient):
        self._client = client

    def notes(self, project: str) -> list[DataFile]:
        return [DataFile.model_validate(item) for item in self._client.get(f"{_base(project)}/notes")]

    def read_note(self, project: str, name: str) -> str:
        return self._client.get(f"{_base(project)}/notes/{segment(name)}")["content"]

    def save_note(self, project: str, name: str, content: str) -> DataFile:
        """Create or overwrite."""
        path = f"{_base(project)}/notes/{segment(name)}"
        return DataFile.model_validate(self._client.put(path, json={"content": content}))

    def delete_note(self, project: str, name: str) -> None:
        self._client.delete(f"{_base(project)}/notes/{segment(name)}")

    def files(self, project: str) -> list[DataFile]:
        return [DataFile.model_validate(item) for item in self._client.get(f"{_base(project)}/files")]

    def read_file(self, project: str, name: str) -> bytes:
        return self._client.get_bytes(f"{_base(project)}/files/{segment(name)}")

    def save_file(self, project: str, name: str, data: bytes) -> DataFile:
        """A file with the same name is overwritten."""
        return DataFile.model_validate(self._client.put_bytes(f"{_base(project)}/files/{segment(name)}", data))

    def delete_file(self, project: str, name: str) -> None:
        self._client.delete(f"{_base(project)}/files/{segment(name)}")


def _base(project: str) -> str:
    return f"/projects/{segment(project)}"
