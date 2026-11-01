"""Git on a project's code folder. A project folder may be a repository itself
or hold several repositories in its subfolders: every call takes the project
plus an optional ``subpath`` inside it, which never escapes the project folder.
Read-only except ``pull_fast_forward``, ``stash``, ``stash_apply``, ``fetch``,
``checkout``, ``create_branch``, ``commit``, ``push`` and ``pull_all_by_branch``.
Nothing here forces, resets, merges or throws local changes away."""
import re
from datetime import datetime
from pathlib import Path

from core.error import AppError, NotFoundError, UpstreamError, ValidationError
from core.observability import LogPrefix, observed
from domain.client.git.client import GitClient
from models.domain.git import (
    GitBranches,
    GitBranchPullOutcome,
    GitBulkStatus,
    GitChangeKind,
    GitCheckoutResult,
    GitCommit,
    GitCommitResult,
    GitDiffResult,
    GitFetchResult,
    GitPullResult,
    GitPushResult,
    GitRepository,
    GitStash,
    GitStashApplyResult,
    GitStashResult,
    GitStatus,
)
from service.store.project_store import ProjectStore

_MAX_LOG = 500
_MAX_PUSHED = 100
_DEFAULT_DIFF_CHARS = 20_000
_MAX_DIFF_CHARS = 200_000
_REJECTED_PUSH = ("rejected", "non-fast-forward", "fetch first")
_STASH_REF = re.compile(r"^(?:stash@\{(\d+)\}|(\d+))$")
_COMMIT_HASH = re.compile(r"^[0-9a-fA-F]{4,40}$")
_SKIPPED_FOLDERS = {"node_modules", "__pycache__", "target", "build", "dist", "venv"}


class GitService:

    def __init__(self, projects: ProjectStore, git: GitClient | None = None):
        self._projects = projects
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

    @observed(LogPrefix.GIT_SERVICE)
    def stash_list(self, project_name: str, subpath: str = "") -> list[GitStash]:
        """The stashes of the repository containing ``subpath``, newest first."""
        _, toplevel = self._repository(project_name, subpath)
        return self._git.stash_list(toplevel)

    @observed(LogPrefix.GIT_SERVICE)
    def fetch(self, project_name: str, subpath: str = "") -> GitFetchResult:
        """``git fetch --all --prune`` of the repository containing ``subpath``:
        downloads, changes no branch nor file. Returns where the current branch
        stands against its upstream afterwards."""
        _, toplevel = self._repository(project_name, subpath)
        self._git.fetch(toplevel)
        status = self._git.status(toplevel)
        return GitFetchResult(branch=status.branch, upstream=status.upstream, ahead=status.ahead, behind=status.behind)

    @observed(LogPrefix.GIT_SERVICE)
    def branches(self, project_name: str, subpath: str = "") -> GitBranches:
        """Local branches (with upstream and ahead/behind) and remote-tracking
        branches of the repository containing ``subpath``."""
        _, toplevel = self._repository(project_name, subpath)
        local = self._git.branches(toplevel)
        current = next((branch.name for branch in local if branch.current), None)
        return GitBranches(current=current, local=local, remote=self._git.remote_branches(toplevel))

    @observed(LogPrefix.GIT_SERVICE)
    def checkout(self, project_name: str, subpath: str = "", branch: str = "") -> GitCheckoutResult:
        """Switch the repository containing ``subpath`` to an existing ``branch``:
        local, or only on a remote (a local branch tracking it is created).
        Refused with uncommitted changes to tracked files."""
        _, toplevel = self._repository(project_name, subpath)
        branch = self._branch_name(toplevel, branch)
        status = self._git.status(toplevel)
        if status.branch == branch:
            return GitCheckoutResult(previous=branch, branch=branch, upstream=status.upstream)
        _refuse_local_changes(status, "branch non cambiato")
        if branch in {item.name for item in self._git.branches(toplevel)}:
            self._git.switch(toplevel, branch)
            created = False
        else:
            self._git.create_branch(toplevel, branch, self._remote_branch(toplevel, branch))
            created = True
        return GitCheckoutResult(previous=status.branch, branch=branch, created=created, upstream=self._git.status(toplevel).upstream)

    @observed(LogPrefix.GIT_SERVICE)
    def create_branch(self, project_name: str, subpath: str = "", name: str = "", start_point: str = "") -> GitCheckoutResult:
        """Create the branch ``name`` and switch to it (``git switch -c``), from
        ``start_point`` (a branch, ``origin/<branch>``, a commit hash; ``""`` =
        the current commit). Uncommitted changes come along to the new branch."""
        _, toplevel = self._repository(project_name, subpath)
        name = self._branch_name(toplevel, name)
        if name in {item.name for item in self._git.branches(toplevel)}:
            raise ValidationError(f"Il branch {name} esiste già: per passarci usa il checkout.")
        start_point = start_point.strip()
        if start_point and (start_point.startswith("-") or not self._git.commit_exists(toplevel, start_point)):
            raise NotFoundError(f"Punto di partenza non trovato: {start_point!r} (un branch, origin/<branch> o un hash).")
        previous = self._git.status(toplevel).branch
        self._git.create_branch(toplevel, name, start_point or None)
        return GitCheckoutResult(previous=previous, branch=name, created=True, upstream=self._git.status(toplevel).upstream)

    @observed(LogPrefix.GIT_SERVICE)
    def diff(self, project_name: str, subpath: str = "", *, staged: bool = False, commit: str = "",
             max_chars: int = _DEFAULT_DIFF_CHARS) -> GitDiffResult:
        """The changes of ``subpath`` (a folder that is not a repository's root
        gets only the files below it): not staged yet (default), staged
        (``staged``) or of one ``commit`` (a hash, also abbreviated). The patch
        is cut at ``max_chars``; the list of files is always complete."""
        if not 1 <= max_chars <= _MAX_DIFF_CHARS:
            raise ValidationError(f"La lunghezza massima del diff deve essere tra 1 e {_MAX_DIFF_CHARS}.")
        folder, toplevel = self._repository(project_name, subpath)
        commit = commit.strip()
        if commit:
            if not _COMMIT_HASH.match(commit):
                raise ValidationError(f"Hash del commit non valido: {commit!r} (4-40 caratteri esadecimali).")
            if not self._git.commit_exists(folder, commit):
                raise NotFoundError(f"Commit non trovato: {commit}")
        only_here = toplevel != folder
        revision = commit or None
        files = self._git.diff_files(folder, staged, revision, only_here)
        patch = self._git.diff_patch(folder, staged, revision, only_here) if files else ""
        untracked = [] if staged or commit else [
            change.path for change in self._git.status(folder, only_here).changes if change.kind is GitChangeKind.UNTRACKED
        ]
        return GitDiffResult(files=files, patch=patch[:max_chars], truncated=len(patch) > max_chars, untracked=untracked)

    @observed(LogPrefix.GIT_SERVICE)
    def commit(self, project_name: str, subpath: str = "", message: str = "", files: list[str] | None = None) -> GitCommitResult:
        """``git add`` + ``git commit`` in the repository containing ``subpath``:
        ``files`` (relative to the repository root, as the status shows them;
        new, changed or deleted) or, when empty, every change below ``subpath``.
        Files staged before are committed too. Refused on a detached HEAD, with
        conflicts or with nothing to commit; the repository's hooks run."""
        message = message.strip()
        if not message:
            raise ValidationError("Il messaggio del commit è obbligatorio.")
        folder, toplevel = self._repository(project_name, subpath)
        status = self._git.status(toplevel)
        if status.branch is None:
            raise ValidationError("HEAD staccato (nessun branch): crea o scegli un branch prima di committare.")
        conflicts = [change.path for change in status.changes if change.kind is GitChangeKind.CONFLICT]
        if conflicts:
            raise ValidationError(f"File in conflitto da risolvere prima del commit: {_shown(conflicts)}.")
        if files:
            self._git.add(toplevel, self._paths_inside(project_name, toplevel, files))
        else:
            self._git.add(folder, ["."])
        staged = self._git.staged_files(toplevel)
        if not staged:
            raise ValidationError("Niente da committare: nessuna modifica nei file indicati.")
        self._git.commit(toplevel, message)
        [created] = self._git.log(toplevel, 1, revision="HEAD")
        return GitCommitResult(branch=status.branch, commit=created, files=staged)

    @observed(LogPrefix.GIT_SERVICE)
    def push(self, project_name: str, subpath: str = "") -> GitPushResult:
        """Push the current branch of the repository containing ``subpath`` to
        its upstream; without one it goes to ``origin`` (or the only remote)
        under the same name and starts tracking it. Never forced: refused when
        the upstream has commits not pulled yet."""
        _, toplevel = self._repository(project_name, subpath)
        status = self._git.status(toplevel)
        branch = status.branch
        if branch is None:
            raise ValidationError("HEAD staccato (nessun branch): il push non si può fare.")
        remote = self._git.config_value(toplevel, f"branch.{branch}.remote")
        merge = self._git.config_value(toplevel, f"branch.{branch}.merge")
        if status.upstream and remote and merge:
            if status.behind:
                raise ValidationError(
                    f"{status.upstream} ha {status.behind} commit che il branch {branch} non ha: fai prima il pull."
                )
            commits = self._git.commits_between(toplevel, status.upstream, "HEAD")
            if commits:
                self._push(toplevel, remote, f"HEAD:{merge}", branch)
            return GitPushResult(branch=branch, upstream=status.upstream, commits=commits)
        remote = self._default_remote(toplevel)
        commits = self._git.unpushed_commits(toplevel, _MAX_PUSHED)
        self._push(toplevel, remote, branch, branch, set_upstream=True)
        upstream = self._git.status(toplevel).upstream or f"{remote}/{branch}"
        return GitPushResult(branch=branch, upstream=upstream, upstream_created=True, commits=commits)

    @observed(LogPrefix.GIT_SERVICE)
    def pull_all_by_branch(self, project_name: str, branch: str) -> list[GitBranchPullOutcome]:
        """For every repository of the project: fetch, switch to ``branch`` (if
        it exists, locally or on a remote) and pull it in fast-forward. A
        repository with uncommitted changes to tracked files, without the
        branch or without an upstream is skipped; one failing does not stop
        the others. One outcome per repository, in path order."""
        root = self._root(project_name)
        branch = self._branch_name(root, branch)
        repositories = self.repositories(project_name)
        if not repositories:
            raise ValidationError("Nessun repository git nella cartella del progetto.")
        return [self._pull_branch(project_name, repository.path, branch) for repository in repositories]

    @observed(LogPrefix.GIT_SERVICE)
    def pull_repository_by_branch(self, project_name: str, subpath: str, branch: str) -> GitBranchPullOutcome:
        """``pull_all_by_branch`` for the one repository containing ``subpath``:
        same steps, same reasons to skip. A folder that is not in the project or
        not in a repository is an error, not a skip."""
        _, toplevel = self._repository(project_name, subpath)
        branch = self._branch_name(toplevel, branch)
        return self._pull_branch(project_name, subpath.strip().strip("/\\"), branch)

    def _pull_branch(self, project_name: str, path: str, branch: str) -> GitBranchPullOutcome:
        outcome = GitBranchPullOutcome(repository=path, status=GitBulkStatus.SKIPPED)
        try:
            _, toplevel = self._repository(project_name, path)
            self._git.fetch(toplevel)
            status = self._git.status(toplevel)
            outcome.previous = status.branch
            if status.branch != branch:
                local = {item.name for item in self._git.branches(toplevel)}
                remote = {name.split("/", 1)[-1] for name in self._git.remote_branches(toplevel)}
                if branch not in local | remote:
                    outcome.reason = f"il branch {branch} non c'è"
                    return outcome
                changed = _tracked_changes(status)
                if changed:
                    outcome.reason = f"modifiche locali non committate: {_shown(changed)}"
                    return outcome
                self.checkout(project_name, path, branch)
                outcome.switched = True
            if not self._git.status(toplevel).upstream:
                outcome.reason = f"il branch {branch} non ha un upstream"
                return outcome
            result = self.pull_fast_forward(project_name, path)
        except ValidationError as exc:
            outcome.reason = str(exc)
            return outcome
        except AppError as exc:
            outcome.status, outcome.reason = GitBulkStatus.FAILED, str(exc)
            return outcome
        outcome.commits = result.commits
        outcome.status = GitBulkStatus.UP_TO_DATE if result.up_to_date else GitBulkStatus.UPDATED
        return outcome

    def repository_folder(self, project_name: str, subpath: str = "") -> Path:
        """``subpath`` (``""`` = the project folder) as an absolute folder,
        checked: inside the project and inside a git repository."""
        folder = self._folder(project_name, subpath)
        if self._git.toplevel(folder) is None:
            raise ValidationError(f"{folder} non è dentro un repository git.")
        return folder

    def head(self, project_name: str, subpath: str = "") -> str:
        """The commit HEAD points to; ``""`` in a repository without commits yet (just ``git init``)."""
        folder = self.repository_folder(project_name, subpath)
        return self._git.head(folder) if self._git.commit_exists(folder, "HEAD") else ""

    def project_folder(self, project_name: str) -> Path | None:
        """The project's code folder as saved (it may not exist any more); None
        for an unknown project. For hiding it in messages."""
        project = self._projects.get(project_name)
        return Path(project.root_path).resolve() if project else None

    # ------------------------------------------------------------- helpers
    def _root(self, project_name: str) -> Path:
        project = self._projects.get(project_name)
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

    def _repository(self, project_name: str, subpath: str) -> tuple[Path, Path]:
        """``subpath`` as a folder and the root of the repository containing it."""
        folder = self._folder(project_name, subpath)
        toplevel = self._git.toplevel(folder)
        if toplevel is None:
            raise ValidationError(f"{folder} non è dentro un repository git.")
        return folder, toplevel

    def _branch_name(self, cwd: Path, name: str) -> str:
        name = name.strip()
        if not name:
            raise ValidationError("Il nome del branch è obbligatorio.")
        if name.startswith("-") or "@{" in name or not self._git.is_valid_branch_name(cwd, name):
            raise ValidationError(f"Nome di branch non valido: {name!r}.")
        return name

    def _remote_branch(self, toplevel: Path, branch: str) -> str:
        """The remote-tracking branch ``<remote>/<branch>`` to start a local
        ``branch`` from: ``origin``'s when several remotes have it."""
        remote_branches = set(self._git.remote_branches(toplevel))
        candidates = [f"{remote}/{branch}" for remote in self._git.remotes(toplevel) if f"{remote}/{branch}" in remote_branches]
        if not candidates:
            raise NotFoundError(f"Branch non trovato, né locale né remoto: {branch} (fai un fetch se è appena stato creato).")
        return f"origin/{branch}" if f"origin/{branch}" in candidates else candidates[0]

    def _default_remote(self, toplevel: Path) -> str:
        remotes = self._git.remotes(toplevel)
        if "origin" in remotes:
            return "origin"
        if len(remotes) == 1:
            return remotes[0]
        if not remotes:
            raise ValidationError("Il repository non ha un remoto: il push non sa dove andare.")
        raise ValidationError(f"Più remoti e nessun upstream ({', '.join(remotes)}): imposta l'upstream a mano.")

    def _push(self, toplevel: Path, remote: str, refspec: str, branch: str, set_upstream: bool = False) -> None:
        try:
            self._git.push(toplevel, remote, refspec, set_upstream)
        except UpstreamError as exc:
            if any(marker in str(exc).lower() for marker in _REJECTED_PUSH):
                raise ValidationError(f"Push rifiutato: il remoto ha commit che il branch {branch} non ha, fai prima il pull.") from exc
            raise

    def _paths_inside(self, project_name: str, toplevel: Path, files: list[str]) -> list[str]:
        """``files`` (relative to the repository root) checked: inside the
        repository and the project folder."""
        root = self._root(project_name)
        paths = []
        for file in files:
            relative = file.strip().strip("/\\")
            path = (toplevel / relative).resolve()
            if not relative or not path.is_relative_to(toplevel) or not path.is_relative_to(root):
                raise ValidationError(f"Il file deve stare dentro il repository: {file!r}")
            paths.append(path.relative_to(toplevel).as_posix())
        return paths


def _tracked_changes(status: GitStatus) -> list[str]:
    return [change.path for change in status.changes if change.kind is not GitChangeKind.UNTRACKED]


def _shown(paths: list[str]) -> str:
    return ", ".join(paths[:10]) + (f" e altri {len(paths) - 10}" if len(paths) > 10 else "")


def _refuse_local_changes(status: GitStatus, what: str) -> None:
    changed = _tracked_changes(status)
    if changed:
        raise ValidationError(f"Modifiche locali non committate, {what}: {_shown(changed)}. Fai prima commit o stash.")


def _stash_ref(stash: str) -> str:
    """``""`` → ``stash@{0}``, ``"2"`` → ``stash@{2}``; ValidationError otherwise."""
    stash = stash.strip()
    if not stash:
        return "stash@{0}"
    match = _STASH_REF.match(stash)
    if match is None:
        raise ValidationError(f"Stash non valido: {stash!r} (es. stash@{{0}} oppure 0).")
    return f"stash@{{{match.group(1) or match.group(2)}}}"
