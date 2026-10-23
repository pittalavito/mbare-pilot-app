"""Response models of the git API (read-only: repositories, log, status)."""
from datetime import datetime

from pydantic import BaseModel

from models.domain.git import GitCommit, GitRepository, GitStatus


class RepositoryResponse(BaseModel):
    path: str
    """Relative to the project folder; ``""`` = the project folder itself."""
    name: str

    @classmethod
    def from_repository(cls, repository: GitRepository) -> "RepositoryResponse":
        return cls(**repository.model_dump())


class CommitResponse(BaseModel):
    hash: str
    short_hash: str
    author: str
    email: str
    date: datetime
    subject: str

    @classmethod
    def from_commit(cls, commit: GitCommit) -> "CommitResponse":
        return cls(**commit.model_dump())


class ChangeResponse(BaseModel):
    path: str
    kind: str
    staged: bool
    unstaged: bool
    original_path: str | None


class StatusResponse(BaseModel):
    branch: str | None
    upstream: str | None
    ahead: int
    behind: int
    is_clean: bool
    changes: list[ChangeResponse]

    @classmethod
    def from_status(cls, status: GitStatus) -> "StatusResponse":
        return cls(**status.model_dump(), is_clean=status.is_clean)
