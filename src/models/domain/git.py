"""Git domain models: the repositories inside a project, their commits and
their working-tree status."""
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class GitRepository(BaseModel):
    """A git repository inside a project folder."""
    path: str
    """Relative to the project folder, with ``/`` separators; ``""`` = the project folder itself."""
    name: str


class GitCommit(BaseModel):
    hash: str
    short_hash: str
    author: str
    email: str
    date: datetime
    """Author date, with its timezone."""
    subject: str


class GitChangeKind(StrEnum):
    MODIFIED = "modified"
    ADDED = "added"
    DELETED = "deleted"
    RENAMED = "renamed"
    COPIED = "copied"
    TYPE_CHANGED = "type_changed"
    UNTRACKED = "untracked"
    CONFLICT = "conflict"


class GitChange(BaseModel):
    """One changed file of the working tree."""
    path: str
    """Relative to the repository root, with ``/`` separators."""
    kind: GitChangeKind
    staged: bool
    """Has changes in the index (``git add``-ed)."""
    unstaged: bool
    """Has changes not added yet (untracked files included)."""
    original_path: str | None = None
    """Previous path of a renamed or copied file."""


class GitStatus(BaseModel):
    branch: str | None
    """Current branch; None when HEAD is detached."""
    upstream: str | None = None
    ahead: int = 0
    """Commits not pushed to the upstream."""
    behind: int = 0
    """Upstream commits not pulled yet."""
    changes: list[GitChange] = []

    @property
    def is_clean(self) -> bool:
        return not self.changes


class GitPullResult(BaseModel):
    """Outcome of a fast-forward pull."""
    branch: str
    upstream: str
    commits: list[GitCommit] = []
    """The commits that arrived, newest first; empty = it was already up to date."""

    @property
    def up_to_date(self) -> bool:
        return not self.commits
