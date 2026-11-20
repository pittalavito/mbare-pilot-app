"""«🗺 Genera mappa dei repository»: the project's repositories
read from their files and git (domain/project/repository_map.py), written
into ``context/repository.md`` (only the generated part changes) and indexed
for the agents' ``search_context``."""
from collections.abc import Callable
from datetime import datetime

from core.error import AppError, NotFoundError
from core.observability import LogPrefix, observed
from domain.dev import tests
from domain.project import repository_map
from models.domain.dev import TestKind
from service.git_service import GitService
from service.project_data_service import ProjectDataService
from service.rag_service import RagService

_BUILD_FILES = {TestKind.MAVEN: "pom.xml", TestKind.NODE: "package.json", TestKind.PYTHON: "pyproject.toml"}


class RepositoryMapService:

    def __init__(self, git: GitService, project_data: ProjectDataService, rag: RagService | None = None,
                 clock: Callable[[], datetime] = datetime.now):
        self._git = git
        self._data = project_data
        self._rag = rag
        self._clock = clock

    @observed(LogPrefix.REPOSITORY_MAP_SERVICE)
    def generate(self, project_name: str) -> tuple[str, str | None]:
        """The map written into the context; the document's name and why it was not indexed (None when it was)."""
        infos = [self._info(project_name, repository.path) for repository in self._git.repositories(project_name)]
        try:
            current = self._data.read_context(project_name, repository_map.DOCUMENT)
        except NotFoundError:
            current = ""
        self._data.save_context(project_name, repository_map.DOCUMENT,
                                repository_map.merge(current, repository_map.render(infos, self._clock())))
        error = self._rag.index_quietly(project_name, repository_map.DOCUMENT) if self._rag else None
        return repository_map.DOCUMENT, error

    def _info(self, project_name: str, path: str) -> repository_map.RepositoryInfo:
        root = self._git.repository_folder(project_name, path)
        files = {item.name for item in root.iterdir()}
        kind = tests.detect(files)
        info = repository_map.RepositoryInfo(path=path, kind=kind, build=tests.install_command(kind, files),
                                             test=tests.default_command(kind, files))
        build_file = root / _BUILD_FILES[kind] if kind in _BUILD_FILES else None
        if build_file is not None and build_file.is_file():
            info.name, info.dependencies = repository_map.identity(kind, build_file.read_text(encoding="utf-8", errors="replace"))
        try:
            branches = self._git.branches(project_name, path)
            info.current = branches.current
            info.branches = repository_map.main_branches([branch.name for branch in branches.local], branches.remote)
        except AppError:
            pass
        return info
