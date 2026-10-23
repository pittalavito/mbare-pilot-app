"""Projects and folders endpoints, typed."""
from urllib.parse import quote

from api_client.http import ApiClient
from api_client.models import FolderListing, Project


class ProjectsApi:

    def __init__(self, client: ApiClient):
        self._client = client

    def all(self) -> list[Project]:
        return [Project.model_validate(item) for item in self._client.get("/projects")]

    def get(self, name: str) -> Project:
        return Project.model_validate(self._client.get(_path(name)))

    def embedding_models(self) -> list[str]:
        return self._client.get("/projects/options")["embedding_models"]

    def open_folder(self, folder: str, name: str = "", description: str = "") -> Project:
        body = {"folder": folder, "name": name, "description": description}
        return Project.model_validate(self._client.post("/projects/open-folder", json=body))

    def create_from_scratch(self, name: str, parent: str, folder_name: str = "", description: str = "") -> Project:
        body = {"name": name, "parent": parent, "folder_name": folder_name, "description": description}
        return Project.model_validate(self._client.post("/projects/from-scratch", json=body))

    def update(self, name: str, description: str, embedding_model: str) -> Project:
        body = {"description": description, "embedding_model": embedding_model}
        return Project.model_validate(self._client.patch(_path(name), json=body))

    def remove(self, name: str) -> None:
        self._client.delete(_path(name))

    # ------------------------------------------------------------- folders
    def folder_roots(self) -> list[str]:
        return self._client.get("/folders/roots")["roots"]

    def list_folder(self, path: str = "", show_hidden: bool = False) -> FolderListing:
        return FolderListing.model_validate(self._client.get("/folders", params={"path": path, "show_hidden": show_hidden}))


def _path(name: str) -> str:
    """Project names may contain spaces or slashes: always encode them."""
    return f"/projects/{quote(name, safe='')}"
