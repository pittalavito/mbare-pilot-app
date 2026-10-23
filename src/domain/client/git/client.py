"""Git commands run with the ``git`` executable in a working folder: no pager,
no credential prompts, no optional locks, bounded time. Output is parsed into
domain models. All read-only except ``pull_fast_forward`` and ``stash_push``."""
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from core.error import UpstreamError
from models.domain.git import GitChange, GitChangeKind, GitCommit, GitStatus

_TIMEOUT_SECONDS = 20
_PULL_TIMEOUT_SECONDS = 120
"""A pull talks to the remote: more time than the local commands."""
_FIELD = "\x1f"
_RECORD = "\x1e"
_LOG_FORMAT = _FIELD.join(["%H", "%h", "%an", "%ae", "%aI", "%s"]) + _RECORD
_ENV = {"GIT_PAGER": "cat", "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0", "LC_ALL": "C"}


class GitClient:

    def __init__(self, executable: str | None = None):
        """``executable`` defaults to ``git`` on PATH."""
        self._executable = executable or shutil.which("git")

    def toplevel(self, cwd: Path) -> Path | None:
        """Root of the repository containing ``cwd``, or None when it is not in one."""
        try:
            output = self._run(cwd, ["rev-parse", "--show-toplevel"])
        except UpstreamError:
            return None
        return Path(output.strip()).resolve()

    def commit_exists(self, cwd: Path, revision: str) -> bool:
        try:
            self._run(cwd, ["rev-parse", "--verify", "--quiet", f"{revision}^{{commit}}"])
        except UpstreamError:
            return False
        return True

    def log(
        self,
        cwd: Path,
        limit: int,
        only_here: bool = False,
        author: str | None = None,
        message: str | None = None,
        revision: str | None = None,
    ) -> list[GitCommit]:
        """The latest ``limit`` commits of the current branch, newest first, or
        only the ``revision`` commit. ``only_here`` keeps only the commits
        touching ``cwd`` and below; ``author`` and ``message`` are plain,
        case-insensitive text matched in the author and in the commit message."""
        args = ["log", f"--max-count={limit}", f"--format={_LOG_FORMAT}", "--regexp-ignore-case", "--fixed-strings"]
        if author:
            args.append(f"--author={author}")
        if message:
            args.append(f"--grep={message}")
        if revision:
            args += ["--no-walk", revision]
        if only_here:
            args += ["--", "."]
        output = self._run(cwd, args)
        return [_parse_commit(record) for record in output.split(_RECORD) if record.strip()]

    def head(self, cwd: Path) -> str:
        """The full hash of the current commit."""
        return self._run(cwd, ["rev-parse", "HEAD"]).strip()

    def commits_between(self, cwd: Path, old: str, new: str) -> list[GitCommit]:
        """The commits reachable from ``new`` but not from ``old``, newest first."""
        output = self._run(cwd, ["log", f"--format={_LOG_FORMAT}", f"{old}..{new}"])
        return [_parse_commit(record) for record in output.split(_RECORD) if record.strip()]

    def pull_fast_forward(self, cwd: Path) -> None:
        """``git pull --ff-only`` of the current branch from its upstream: never
        a merge. UpstreamError when it cannot fast-forward or the remote fails."""
        self._run(cwd, ["pull", "--ff-only", "--no-rebase"], timeout=_PULL_TIMEOUT_SECONDS)

    def stash_push(self, cwd: Path, message: str) -> bool:
        """``git stash push -m message``: puts aside the changes to tracked files
        (untracked ones stay). False when there was nothing to put aside."""
        output = self._run(cwd, ["stash", "push", "-m", message])
        return "No local changes to save" not in output

    def status(self, cwd: Path, only_here: bool = False) -> GitStatus:
        """Branch and changed files of the working tree (untracked included,
        ignored excluded). ``only_here`` keeps only the files in ``cwd`` and below."""
        args = ["status", "--porcelain=v2", "--branch", "-z", "--untracked-files=normal"]
        if only_here:
            args += ["--", "."]
        return _parse_status(self._run(cwd, args))

    def _run(self, cwd: Path, args: list[str], timeout: int = _TIMEOUT_SECONDS) -> str:
        if not self._executable:
            raise UpstreamError("git non trovato: installalo e mettilo nel PATH.")
        command = [self._executable, "-c", "core.fsmonitor=false", "-c", "i18n.logOutputEncoding=UTF-8", *args]
        try:
            result = subprocess.run(
                command, cwd=cwd, env={**os.environ, **_ENV}, capture_output=True,
                encoding="utf-8", errors="replace", timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise UpstreamError(f"git {args[0]} non ha risposto entro {timeout}s ({cwd}).") from exc
        except OSError as exc:
            raise UpstreamError(f"Impossibile eseguire git: {exc}") from exc
        if result.returncode != 0:
            raise UpstreamError(f"git {args[0]} fallito ({cwd}): {result.stderr.strip() or result.returncode}")
        return result.stdout


_KINDS = {
    "M": GitChangeKind.MODIFIED, "A": GitChangeKind.ADDED, "D": GitChangeKind.DELETED,
    "R": GitChangeKind.RENAMED, "C": GitChangeKind.COPIED, "T": GitChangeKind.TYPE_CHANGED,
}


def _parse_status(output: str) -> GitStatus:
    """``git status --porcelain=v2 --branch -z``: NUL-separated entries; a
    rename/copy entry (``2``) is followed by its original path."""
    status = GitStatus(branch=None)
    tokens = iter(output.split("\0"))
    for token in tokens:
        if not token:
            continue
        if token.startswith("# branch.head "):
            head = token.removeprefix("# branch.head ")
            status.branch = None if head == "(detached)" else head
        elif token.startswith("# branch.upstream "):
            status.upstream = token.removeprefix("# branch.upstream ")
        elif token.startswith("# branch.ab "):
            ahead, behind = token.removeprefix("# branch.ab ").split()
            status.ahead, status.behind = int(ahead), -int(behind)
        elif token.startswith("? "):
            status.changes.append(GitChange(
                path=token[2:], kind=GitChangeKind.UNTRACKED, staged=False, unstaged=True,
            ))
        elif token[:2] in ("1 ", "2 ", "u "):
            status.changes.append(_parse_change(token, next(tokens) if token[0] == "2" else None))
    return status


def _parse_change(token: str, original_path: str | None) -> GitChange:
    """Ordinary (``1``), renamed/copied (``2``) or unmerged (``u``) entry: the
    path is the last field, after a type-specific number of fields."""
    entry_type, xy = token[0], token[2:4]
    fields_before_path = {"1": 8, "2": 9, "u": 10}[entry_type]
    path = token.split(" ", fields_before_path)[fields_before_path]
    if entry_type == "u":
        return GitChange(path=path, kind=GitChangeKind.CONFLICT, staged=False, unstaged=True)
    index, worktree = xy
    return GitChange(
        path=path,
        kind=_KINDS.get(worktree if worktree != "." else index, GitChangeKind.MODIFIED),
        staged=index != ".",
        unstaged=worktree != ".",
        original_path=original_path,
    )


def _parse_commit(record: str) -> GitCommit:
    full_hash, short_hash, author, email, date, subject = record.strip("\n").split(_FIELD, 5)
    return GitCommit(
        hash=full_hash, short_hash=short_hash, author=author, email=email,
        date=datetime.fromisoformat(date), subject=subject,
    )
