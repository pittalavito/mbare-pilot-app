"""Project domain models: a project is a named folder on disk the agents work on."""
from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from models.domain.chat import EmbeddingModelName

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class ProjectSource(StrEnum):
    """Where a project comes from."""
    FOLDER = "folder"
    """An existing folder opened as a project."""
    SCRATCH = "scratch"
    """A new, empty folder created for the project."""


class Project(BaseModel):
    name: Name
    description: str = ""
    source: ProjectSource
    root_path: str
    """Absolute path of the project folder."""
    embedding_model: EmbeddingModelName = EmbeddingModelName.OPENAI_TEXT_EMBEDDING_3_SMALL
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProjectDataKind(StrEnum):
    NOTE = "note"
    """Markdown note written in the app."""
    FILE = "file"
    """Uploaded document."""


class ProjectDataFile(BaseModel):
    """One item of a project's data folder."""
    name: str
    kind: ProjectDataKind
    size: int
    modified_at: datetime
