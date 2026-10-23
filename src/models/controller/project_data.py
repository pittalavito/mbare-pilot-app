"""Request/response models of a project's data API (notes and uploaded files)."""
from datetime import datetime

from pydantic import BaseModel

from models.domain.project import ProjectDataFile


class DataFileResponse(BaseModel):
    name: str
    kind: str
    """``note`` | ``file``."""
    size: int
    modified_at: datetime

    @classmethod
    def from_file(cls, item: ProjectDataFile) -> "DataFileResponse":
        return cls(**item.model_dump())


class NoteResponse(BaseModel):
    name: str
    content: str


class NoteRequest(BaseModel):
    content: str
