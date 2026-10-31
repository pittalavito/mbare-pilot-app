"""Git commands run with the ``git`` executable in a working folder: no pager,
no credential prompts, no optional locks, bounded time. Output is parsed into
domain models. Read-only except ``pull_fast_forward``, ``stash_push``,
``stash_apply``, ``fetch``, ``switch``, ``create_branch``, ``add``, ``commit``
and ``push`` (never forced)."""
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from core.error import UpstreamError
from models.domain.git import GitBranch, GitChange, GitChangeKind, GitCommit, GitDiffFile, GitStash, GitStatus

_TIMEOUT_SECONDS = 20
_REMOTE_TIMEOUT_SECONDS = 120
"""Pull, fetch and push talk to the remote: more time than the local commands."""
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
        self._run(cwd, ["pull", "--ff-only", "--no-rebase"], timeout=_REMOTE_TIMEOUT_SECONDS)

    def stash_push(self, cwd: Path, message: str) -> bool:
        """``git stash push -m message``: puts aside the changes to tracked files
        (untracked ones stay). False when there was nothing to put aside."""
        output = self._run(cwd, ["stash", "push", "-m", message])
        return "No local changes to save" not in output

    def stash_list(self, cwd: Path) -> list[GitStash]:
        """The stashes, newest first."""
        output = self._run(cwd, ["stash", "list", f"--format=%gd{_FIELD}%gs"])
        return [GitStash(ref=ref, message=message) for ref, message in
                (line.split(_FIELD, 1) for line in output.splitlines() if _FIELD in line)]

    def stash_apply(self, cwd: Path, ref: str) -> None:
        """``git stash apply <ref>``: the stash stays in the list. UpstreamError
        when it does not apply cleanly (conflicts are left in the working tree)."""
        self._run(cwd, ["stash", "apply", ref])

    def fetch(self, cwd: Path) -> None:
        """``git fetch --all --prune``: every remote, deleted remote branches forgotten."""
        self._run(cwd, ["fetch", "--all", "--prune", "--quiet"], timeout=_REMOTE_TIMEOUT_SECONDS)

    def branches(self, cwd: Path) -> list[GitBranch]:
        """The local branches, sorted by name."""
        fields = ["%(refname:short)", "%(HEAD)", "%(upstream:short)", "%(upstream:track,nobracket)",
                  "%(objectname:short)", "%(committerdate:iso-strict)", "%(contents:subject)"]
        output = self._run(cwd, ["for-each-ref", f"--format={_FIELD.join(fields)}{_RECORD}", "refs/heads"])
        return [_parse_branch(record) for record in output.split(_RECORD) if record.strip()]

    def remote_branches(self, cwd: Path) -> list[str]:
        """The remote-tracking branches (``origin/main``), without the remotes' ``HEAD``."""
        output = self._run(cwd, ["for-each-ref", f"--format=%(refname:short){_FIELD}%(symref)", "refs/remotes"])
        return [name for name, symref in (line.split(_FIELD, 1) for line in output.splitlines() if _FIELD in line) if not symref]

    def remotes(self, cwd: Path) -> list[str]:
        return [line.strip() for line in self._run(cwd, ["remote"]).splitlines() if line.strip()]

    def is_valid_branch_name(self, cwd: Path, name: str) -> bool:
        try:
            self._run(cwd, ["check-ref-format", "--branch", name])
        except UpstreamError:
            return False
        return True

    def switch(self, cwd: Path, branch: str) -> None:
        """``git switch <branch>``: a branch only on one remote becomes a local
        branch tracking it. UpstreamError when it does not exist or local
        changes would be overwritten."""
        self._run(cwd, ["switch", "--quiet", branch])

    def create_branch(self, cwd: Path, name: str, start_point: str | None = None) -> None:
        """``git switch -c <name> [<start_point>]``: from a remote branch it tracks it."""
        self._run(cwd, ["switch", "--quiet", "-c", name, *([start_point] if start_point else [])])

    def diff_files(self, cwd: Path, staged: bool = False, revision: str | None = None, only_here: bool = False) -> list[GitDiffFile]:
        """``--numstat`` of the working tree against the index, of the index
        against HEAD (``staged``) or of the ``revision`` commit."""
        output = self._run(cwd, [*_diff_args(staged, revision), "--numstat", "-z", *(["--", "."] if only_here else [])])
        return _parse_numstat(output)

    def diff_patch(self, cwd: Path, staged: bool = False, revision: str | None = None, only_here: bool = False) -> str:
        return self._run(cwd, [*_diff_args(staged, revision), "--patch", *(["--", "."] if only_here else [])])

    def add(self, cwd: Path, paths: list[str]) -> None:
        """``git add -A -- <paths>``: new, changed and deleted files."""
        self._run(cwd, ["add", "-A", "--", *paths])

    def staged_files(self, cwd: Path) -> list[str]:
        output = self._run(cwd, ["diff", "--cached", "--name-only", "-z"])
        return [path for path in output.split("\0") if path]

    def commit(self, cwd: Path, message: str) -> None:
        """``git commit`` of the index; the repository's hooks run."""
        self._run(cwd, ["commit", "--quiet", "-m", message])

    def config_value(self, cwd: Path, key: str) -> str | None:
        try:
            return self._run(cwd, ["config", "--get", key]).strip() or None
        except UpstreamError:
            return None

    def unpushed_commits(self, cwd: Path, limit: int) -> list[GitCommit]:
        """The commits of HEAD that no remote branch has, newest first."""
        output = self._run(cwd, ["log", f"--max-count={limit}", f"--format={_LOG_FORMAT}", "HEAD", "--not", "--remotes"])
        return [_parse_commit(record) for record in output.split(_RECORD) if record.strip()]

    def push(self, cwd: Path, remote: str, refspec: str, set_upstream: bool = False) -> None:
        """``git push [-u] <remote> <refspec>``: never forced."""
        self._run(cwd, ["push", "--quiet", *(["-u"] if set_upstream else []), remote, refspec], timeout=_REMOTE_TIMEOUT_SECONDS)

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


def _diff_args(staged: bool, revision: str | None) -> list[str]:
    base = ["--no-color", "--no-ext-diff", "--find-renames"]
    if revision:
        return ["show", "--format=", *base, revision]
    return ["diff", *base, *(["--cached"] if staged else [])]


def _parse_numstat(output: str) -> list[GitDiffFile]:
    """``--numstat -z``: ``added<TAB>deleted<TAB>path<NUL>``; a rename has an
    empty path followed by the old and the new path. Binary files have ``-``."""
    files: list[GitDiffFile] = []
    tokens = iter(output.split("\0"))
    for token in tokens:
        token = token.lstrip("\n")
        if not token:
            continue
        added, deleted, path = token.split("\t", 2)
        if not path:
            next(tokens)  # the old path
            path = next(tokens)
        binary = added == "-"
        files.append(GitDiffFile(path=path, added=0 if binary else int(added), deleted=0 if binary else int(deleted), binary=binary))
    return files


_TRACK = re.compile(r"(ahead|behind) (\d+)")


def _parse_branch(record: str) -> GitBranch:
    name, head, upstream, track, short_hash, date, subject = record.strip("\n").split(_FIELD, 6)
    counts = {kind: int(count) for kind, count in _TRACK.findall(track)}
    return GitBranch(
        name=name, current=head == "*", upstream=upstream or None,
        ahead=counts.get("ahead", 0), behind=counts.get("behind", 0), upstream_gone=track == "gone",
        last_commit=short_hash, last_commit_date=datetime.fromisoformat(date) if date else None, last_subject=subject,
    )


def _parse_commit(record: str) -> GitCommit:
    full_hash, short_hash, author, email, date, subject = record.strip("\n").split(_FIELD, 5)
    return GitCommit(
        hash=full_hash, short_hash=short_hash, author=author, email=email,
        date=datetime.fromisoformat(date), subject=subject,
    )
