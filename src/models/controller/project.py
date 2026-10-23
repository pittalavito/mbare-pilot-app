"""Request/response models of the projects and folders API. They are the API
contract: domain models never leave the controllers."""
from datetime import datetime

from pydantic import BaseModel

from models.domain.chat import EmbeddingModelName
from models.domain.project import Project, ProjectSource


class ProjectResponse(BaseModel):
    name: str
    description: str
    source: ProjectSource
    root_path: str
    embedding_model: EmbeddingModelName
    created_at: datetime
    folder_exists: bool
    """False when the project folder was deleted or moved on disk."""

    @classmethod
    def from_project(cls, project: Project, folder_exists: bool) -> "ProjectResponse":
        return cls(**project.model_dump(), folder_exists=folder_exists)


class ProjectOptionsResponse(BaseModel):
    """Choices the UI offers when creating or editing a project."""
    embedding_models: list[EmbeddingModelName]


class OpenFolderRequest(BaseModel):
    folder: str
    name: str = ""
    """Empty = the folder's name."""
    description: str = ""


class CreateFromScratchRequest(BaseModel):
    name: str
    parent: str
    """Folder the new project folder is created in."""
    folder_name: str = ""
    """Empty = the project's name."""
    description: str = ""


class UpdateProjectRequest(BaseModel):
    description: str
    embedding_model: EmbeddingModelName


class FolderEntry(BaseModel):
    name: str
    path: str


class FolderListingResponse(BaseModel):
    """One folder of the picker: where you are, where "up" goes, what is inside."""
    path: str
    parent: str | None
    """None at a root."""
    subfolders: list[FolderEntry]


class FolderRootsResponse(BaseModel):
    roots: list[str]
