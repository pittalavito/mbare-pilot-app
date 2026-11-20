"""A free search in a project's code (plan 23), for the user (Progetto → Git,
«🔎 Cerca nel codice») and for the agents (tools ``search_code`` and, for Dev,
``save_code_search``).

``search`` reads the files git knows in each repository of the project (or
the one asked: tracked, plus new ones not ignored, so ``.gitignore`` is
respected), skipping binaries, files that are not UTF-8 and big files. ``save`` writes the matches as
a code reference (one per search title, rewritten when saved again) and links
it from the agent tasks asked."""
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path

from core.error import ConflictError, NotFoundError
from core.observability import LogPrefix, observed
from domain.project import code_search
from domain.project.data_paths import typed_note_file_name
from models.domain.code_search import CodeMatch, CodeQuery, CodeSearchResult, CodeSearchSaved
from models.domain.note import NoteType
from service.git_service import GitService
from service.project_data_service import ProjectDataService

MAX_FILE_BYTES = 1_000_000
"""Bigger files are skipped (generated code, data, minified bundles)."""
SAVED_MATCHES = 500
"""At most this many matches go in a reference."""
_BINARY_PROBE = 8192


class CodeSearchService:

    def __init__(self, git_service: GitService, project_data_service: ProjectDataService,
                 clock: Callable[[], datetime] = datetime.now):
        self._git = git_service
        self._data = project_data_service
        self._clock = clock

    @observed(LogPrefix.CODE_SEARCH_SERVICE)
    def search(self, project_name: str, query: CodeQuery, limit: int = 200, chars: int = code_search.LINE_CHARS) -> CodeSearchResult:
        """The matches, at most ``limit`` (the total and how many files say the rest); 400 for a broken regex,
        404 for a repository that is not in the project."""
        found = code_search.pattern(query)
        repositories = [repository.path for repository in self._git.repositories(project_name)]
        if query.repository.strip():
            wanted = query.repository.strip().strip("/\\")
            if wanted not in repositories:
                raise NotFoundError(f"Repository non trovato nel progetto: {wanted}")
            repositories = [wanted]
        matches: list[CodeMatch] = []
        total, files = 0, 0
        for repository in repositories:
            folder = self._git.repository_folder(project_name, repository)
            for path in self._git.files(project_name, repository):
                if not code_search.wanted(path, query.files):
                    continue
                text = _read_text(folder / path)
                if not text:
                    continue
                here = code_search.find(text, f"{repository}/{path}" if repository else path, found, chars)
                if here:
                    files += 1
                    total += len(here)
                    matches += here[: max(0, limit - len(matches))]
        return CodeSearchResult(matches=matches, total=total, files=files, truncated=total > len(matches))

    @observed(LogPrefix.CODE_SEARCH_SERVICE)
    def save(self, project_name: str, query: CodeQuery, title: str = "", link_to: Sequence[str] = ()) -> CodeSearchSaved:
        """The search as a code reference titled ``title`` (``""`` = the text searched), linked from ``link_to``
        (agent tasks or activities). ConflictError when a reference with that name exists and was not
        written by a search (it is left as it is)."""
        result = self.search(project_name, query, limit=SAVED_MATCHES)
        title = " ".join((title or query.query).split())
        name = typed_note_file_name(NoteType.CODE_REFERENCE, title)
        try:
            existing = self._data.reference(project_name, name)[1]
        except NotFoundError:
            existing = None
        if existing is not None and existing.source != code_search.SOURCE:
            raise ConflictError(f"Esiste già {name}, non scritto da una ricerca: scegli un altro titolo.")
        reference = code_search.reference(title, query, result.matches, result.total, self._clock())
        if existing is None:
            name = self._data.create_reference(project_name, NoteType.CODE_REFERENCE, reference)
        else:
            self._data.save_reference(project_name, name, reference)
        if link_to:
            self._data.link_reference(project_name, name, list(link_to))
        return CodeSearchSaved(note=name, created=existing is None, total=result.total)


def _read_text(path: Path) -> str:
    """The file as text; ``""`` when it is missing, big, binary or not UTF-8."""
    try:
        if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            return ""
        data = path.read_bytes()
    except OSError:
        return ""
    if b"\0" in data[:_BINARY_PROBE]:
        return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return ""
