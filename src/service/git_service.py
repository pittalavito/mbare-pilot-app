"""Git on a project's code folder. A project folder may be a repository itself
or hold several repositories in its subfolders: every call takes the project
plus an optional ``subpath`` inside it, which never escapes the project folder.
Everything is read-only except ``pull_fast_forward``, ``stash`` and ``stash_apply``."""
import re
from datetime import datetime
from pathlib import Path

from core.error import NotFoundError, UpstreamError, ValidationError
from core.observability import LogPrefix, observed
from domain.client.git.client import GitClient
from models.domain.git import GitChangeKind, GitCommit, GitPullResult, GitRepository, GitStashApplyResult, GitStashResult, GitStatus
from service.store_service import StoreService

_MAX_LOG = 500
_STASH_REF = re.compile(r"^(?:stash@\{(\d+)\}|(\d+))$")
_COMMIT_HASH = re.compile(r"^[0-9a-fA-F]{4,40}$")
_SKIPPED_FOLDERS = {"node_modules", "__pycache__", "target", "build", "dist", "venv"}


class GitService:

    def __init__(self, store_service: StoreService, git: GitClient | None = None):
        self._store = store_service
        self._git = git or GitClient()

    def repositories(self, project_name: str, max_depth: int = 2) -> list[GitRepository]:
        """Git repositories in the project folder (itself included), down to
        ``max_depth`` levels, sorted by path. Nested repositories are not searched."""
        root = self._root(project_name)
        found: list[GitRepository] = []

        def visit(folder: Path, depth: int) -> None:
            if (folder / ".git").exists():
                relative = folder.relative_to(root).as_posix()
                found.append(GitRepository(path="" if relative == "." else relative, name=folder.name))
                return
            if depth >= max_depth:
                return
            try:
                children = sorted(child for child in folder.iterdir() if child.is_dir())
            except OSError:
                return
            for child in children:
                if not child.name.startswith(".") and child.name not in _SKIPPED_FOLDERS:
                    visit(child, depth + 1)

        visit(root, 0)
        return sorted(found, key=lambda repo: repo.path.lower())

    @observed(LogPrefix.GIT_SERVICE)
    def log(
        self,
        project_name: str,
        subpath: str = "",
        limit: int = 50,
        *,
        author: str = "",
        message: str = "",
        commit: str = "",
    ) -> list[GitCommit]:
        """``git log`` of ``subpath`` (a folder inside the project, ``""`` = the
        project folder), newest first. A folder that is not a repository's root
        gets only the commits touching it. Optional filters, all combinable:
        ``author`` and ``message`` (text contained, case-insensitive) and
        ``commit`` (a hash, also abbreviated: that commit only, if it matches
        the other filters)."""
        if not 1 <= limit <= _MAX_LOG:
            raise ValidationError(f"Il numero di commit deve essere tra 1 e {_MAX_LOG}.")
        commit = commit.strip()
        if commit and not _COMMIT_HASH.match(commit):
            raise ValidationError(f"Hash del commit non valido: {commit!r} (4-40 caratteri esadecimali).")
        folder = self._folder(project_name, subpath)
        toplevel = self._git.toplevel(folder)
        if toplevel is None:
            raise ValidationError(f"{folder} non è dentro un repository git.")
        if commit and not self._git.commit_exists(folder, commit):
            raise NotFoundError(f"Commit non trovato: {commit}")
        return self._git.log(
            folder,
            limit,
            only_here=toplevel != folder and not commit,
            author=author.strip() or None,
            message=message.strip() or None,
            revision=commit or None
        )

    @observed(LogPrefix.GIT_SERVICE)
    def status(self, project_name: str, subpath: str = "") -> GitStatus:
        """``git status`` of ``subpath`` (a folder inside the project, ``""`` =
        the project folder): branch, ahead/behind its upstream and the changed
        files (staged, unstaged, untracked). A folder that is not a repository's
        root gets only the files below it; paths stay relative to the repository root."""
        folder = self._folder(project_name, subpath)
        toplevel = self._git.toplevel(folder)
        if toplevel is None:
            raise ValidationError(f"{folder} non è dentro un repository git.")
        return self._git.status(folder, only_here=toplevel != folder)

    @observed(LogPrefix.GIT_SERVICE)
    def pull_fast_forward(self, project_name: str, subpath: str = "") -> GitPullResult:
        """Bring the current branch of the repository containing ``subpath`` up
        to date with its upstream, only if that needs no merge (``--ff-only``).
        Refused when HEAD is detached, the branch has no upstream or tracked
        files have uncommitted changes (untracked files are fine)."""
        folder = self._folder(project_name, subpath)
        toplevel = self._git.toplevel(folder)
        if toplevel is None:
            raise ValidationError(f"{folder} non è dentro un repository git.")
        status = self._git.status(toplevel)
        if status.branch is None:
            raise ValidationError("HEAD staccato (nessun branch): il pull non si può fare.")
        if not status.upstream:
            raise ValidationError(f"Il branch {status.branch} non ha un upstream: il pull non sa da dove aggiornare.")
        changed = [change.path for change in status.changes if change.kind is not GitChangeKind.UNTRACKED]
        if changed:
            shown = ", ".join(changed[:10]) + (f" e altri {len(changed) - 10}" if len(changed) > 10 else "")
            raise ValidationError(f"Modifiche locali non committate, pull non fatto: {shown}.")
        before = self._git.head(toplevel)
        try:
            self._git.pull_fast_forward(toplevel)
        except UpstreamError as exc:
            if "fast-forward" in str(exc).lower():
                raise ValidationError(
                    f"Il branch {status.branch} ha commit locali che {status.upstream} non ha: "
                    "il fast-forward non è possibile, serve un merge o un rebase fatto a mano."
                ) from exc
            raise
        after = self._git.head(toplevel)
        commits = [] if after == before else self._git.commits_between(toplevel, before, after)
        return GitPullResult(branch=status.branch, upstream=status.upstream, commits=commits)

    @observed(LogPrefix.GIT_SERVICE)
    def stash(self, project_name: str, subpath: str = "", message: str = "") -> GitStashResult:
        """Put aside the uncommitted changes to tracked files of the repository
        containing ``subpath`` (``git stash push``); untracked files stay. An
        empty ``message`` becomes ``mbare-pilot <date time>``."""
        folder = self._folder(project_name, subpath)
        toplevel = self._git.toplevel(folder)
        if toplevel is None:
            raise ValidationError(f"{folder} non è dentro un repository git.")
        files = [change.path for change in self._git.status(toplevel).changes if change.kind is not GitChangeKind.UNTRACKED]
        message = message.strip() or f"mbare-pilot {datetime.now():%Y-%m-%d %H:%M}"
        if not files or not self._git.stash_push(toplevel, message):
            return GitStashResult(stashed=False, message=message)
        return GitStashResult(stashed=True, ref="stash@{0}", message=message, files=files)

    @observed(LogPrefix.GIT_SERVICE)
    def stash_apply(self, project_name: str, subpath: str = "", stash: str = "") -> GitStashApplyResult:
        """Apply a stash of the repository containing ``subpath`` (``git stash
        apply``): ``stash`` is ``stash@{n}`` or ``n``, empty = the newest. The
        stash stays in the list. Refused with uncommitted changes to tracked
        files; conflicts are reported, not undone."""
        folder = self._folder(project_name, subpath)
        toplevel = self._git.toplevel(folder)
        if toplevel is None:
            raise ValidationError(f"{folder} non è dentro un repository git.")
        ref = _stash_ref(stash)
        stashes = {entry.ref: entry for entry in self._git.stash_list(toplevel)}
        if not stashes:
            raise NotFoundError("Nessuno stash in questo repository.")
        if ref not in stashes:
            raise NotFoundError(f"Stash {ref} non trovato. Stash disponibili: {', '.join(stashes)}.")
        changed = [c.path for c in self._git.status(toplevel).changes if c.kind is not GitChangeKind.UNTRACKED]
        if changed:
            shown = ", ".join(changed[:10]) + (f" e altri {len(changed) - 10}" if len(changed) > 10 else "")
            raise ValidationError(f"Modifiche locali non committate, stash non applicato: {shown}.")
        try:
            self._git.stash_apply(toplevel, ref)
        except UpstreamError:
            conflicts = [c.path for c in self._git.status(toplevel).changes if c.kind is GitChangeKind.CONFLICT]
            if not conflicts:
                raise
            return GitStashApplyResult(ref=ref, message=stashes[ref].message, conflicts=conflicts)
        files = [c.path for c in self._git.status(toplevel).changes if c.kind is not GitChangeKind.UNTRACKED]
        return GitStashApplyResult(ref=ref, message=stashes[ref].message, files=files)

    def repository_folder(self, project_name: str, subpath: str = "") -> Path:
        """``subpath`` (``""`` = the project folder) as an absolute folder,
        checked: inside the project and inside a git repository."""
        folder = self._folder(project_name, subpath)
        if self._git.toplevel(folder) is None:
            raise ValidationError(f"{folder} non è dentro un repository git.")
        return folder

    def root_folder(self, project_name: str) -> Path:
        """The project folder, checked: it exists (it need not be a repository)."""
        return self._root(project_name)

    def head(self, project_name: str, subpath: str = "") -> str:
        """The commit HEAD points to; ``""`` in a repository without commits yet (just ``git init``)."""
        folder = self.repository_folder(project_name, subpath)
        return self._git.head(folder) if self._git.commit_exists(folder, "HEAD") else ""

    def project_folder(self, project_name: str) -> Path | None:
        """The project's code folder as saved (it may not exist any more); None
        for an unknown project. For hiding it in messages."""
        project = self._store.get_project(project_name)
        return Path(project.root_path).resolve() if project else None

    # ------------------------------------------------------------- helpers
    def _root(self, project_name: str) -> Path:
        project = self._store.get_project(project_name)
        if project is None:
            raise NotFoundError(f"Progetto non trovato: {project_name}")
        root = Path(project.root_path).resolve()
        if not root.is_dir():
            raise NotFoundError(f"La cartella del progetto non esiste più: {root}")
        return root

    def _folder(self, project_name: str, subpath: str) -> Path:
        """``subpath`` resolved inside the project folder; ValidationError when
        it leaves the folder or is not a directory."""
        root = self._root(project_name)
        folder = (root / subpath.strip().strip("/\\")).resolve()
        if not folder.is_relative_to(root):
            raise ValidationError(f"Il percorso deve stare dentro il progetto: {subpath!r}")
        if not folder.is_dir():
            raise ValidationError(f"Cartella inesistente nel progetto: {subpath!r}")
        return folder


def _stash_ref(stash: str) -> str:
    """``""`` → ``stash@{0}``, ``"2"`` → ``stash@{2}``; ValidationError otherwise."""
    stash = stash.strip()
    if not stash:
        return "stash@{0}"
    match = _STASH_REF.match(stash)
    if match is None:
        raise ValidationError(f"Stash non valido: {stash!r} (es. stash@{{0}} oppure 0).")
    return f"stash@{{{match.group(1) or match.group(2)}}}"
