"""Git on a project's code folder. A project folder may be a repository itself
or hold several repositories in its subfolders: every call takes the project
plus an optional ``subpath`` inside it, which never escapes the project folder."""
import re
from pathlib import Path

from core.error import NotFoundError, ValidationError
from core.observability import LogPrefix, observed
from domain.client.git.client import GitClient
from models.domain.git import GitCommit, GitRepository, GitStatus
from service.store_service import StoreService

_MAX_LOG = 500
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
            folder, limit, only_here=toplevel != folder and not commit,
            author=author.strip() or None, message=message.strip() or None, revision=commit or None,
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
