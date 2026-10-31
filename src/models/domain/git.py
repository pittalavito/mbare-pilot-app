"""Git domain models: the repositories inside a project, their commits,
branches, diffs and working-tree status, and the outcomes of the commands
that change them."""
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from models.domain.masking import MaskEmailAddress, MaskPersonName, MaskRepositoryName


class GitRepository(BaseModel):
    """A git repository inside a project folder."""
    path: str
    """Relative to the project folder, with ``/`` separators; ``""`` = the project folder itself."""
    name: str


class GitCommit(BaseModel):
    hash: str
    short_hash: str
    author: MaskPersonName
    email: MaskEmailAddress
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


class GitStashResult(BaseModel):
    """Outcome of a ``git stash push``."""
    stashed: bool
    """False when there was nothing to put aside."""
    ref: str | None = None
    """``stash@{0}``: the new stash, on top of the list."""
    message: str = ""
    files: list[str] = []
    """The tracked files put aside."""


class GitStash(BaseModel):
    """One entry of ``git stash list``."""
    ref: str
    """``stash@{n}``, 0 = the newest."""
    message: str


class GitStashApplyResult(BaseModel):
    """Outcome of a ``git stash apply`` (the stash always stays in the list)."""
    ref: str
    message: str
    files: list[str] = []
    """The files changed in the working tree after applying."""
    conflicts: list[str] = []
    """Files left in conflict, to resolve by hand; empty = applied cleanly."""


class GitBranch(BaseModel):
    """One local branch (``git for-each-ref refs/heads``)."""
    name: str
    current: bool = False
    upstream: str | None = None
    ahead: int = 0
    behind: int = 0
    upstream_gone: bool = False
    """The upstream was deleted on the remote (e.g. after merging its pull request)."""
    last_commit: str = ""
    """Short hash of its latest commit."""
    last_commit_date: datetime | None = None
    last_subject: str = ""


class GitBranches(BaseModel):
    current: str | None
    """None when HEAD is detached."""
    local: list[GitBranch] = []
    remote: list[str] = []
    """Remote-tracking branches, e.g. ``origin/main`` (as of the last fetch)."""


class GitFetchResult(BaseModel):
    """Outcome of ``git fetch --all --prune``: where the current branch stands now."""
    branch: str | None
    upstream: str | None = None
    ahead: int = 0
    behind: int = 0
    """Commits that arrived on the upstream and are not pulled yet."""


class GitCheckoutResult(BaseModel):
    """Outcome of switching (or creating and switching) branch."""
    previous: str | None
    """The branch before; None when HEAD was detached."""
    branch: str
    created: bool = False
    """A new branch (``git switch -c``, or a local one made from a remote branch)."""
    upstream: str | None = None


class GitDiffFile(BaseModel):
    path: str
    """Relative to the repository root."""
    added: int = 0
    deleted: int = 0
    binary: bool = False


class GitDiffResult(BaseModel):
    """``git diff``: of the working tree, of the index (``staged``) or of one commit."""
    files: list[GitDiffFile] = []
    patch: str = ""
    truncated: bool = False
    """The patch was cut at the length limit (``files`` is always complete)."""
    untracked: list[str] = []
    """New files git does not track yet: not in the patch (working-tree diff only)."""


class GitCommitResult(BaseModel):
    """Outcome of ``git add`` + ``git commit``."""
    branch: str
    commit: GitCommit
    files: list[str] = []
    """The files in the commit."""


class GitPushResult(BaseModel):
    branch: str
    upstream: str
    upstream_created: bool = False
    """The branch had no upstream: it was pushed with ``-u`` and now tracks it."""
    commits: list[GitCommit] = []
    """The commits sent, newest first; empty = nothing to push."""


class GitBulkStatus(StrEnum):
    UPDATED = "updated"
    UP_TO_DATE = "up_to_date"
    SKIPPED = "skipped"
    """Not touched: the reason says why (branch missing, local changes, ...)."""
    FAILED = "failed"


class GitBranchPullOutcome(BaseModel):
    """What happened to one repository in ``pull_all_by_branch``."""
    repository: MaskRepositoryName
    status: GitBulkStatus
    previous: str | None = None
    """The branch it was on before."""
    switched: bool = False
    commits: list[GitCommit] = []
    reason: str = ""
