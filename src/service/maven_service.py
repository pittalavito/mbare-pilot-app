"""Maven on a project's repositories: their root ``pom.xml`` read from the
working tree (the branch each repository is on, uncommitted changes
included) and compared with a parent POM. Read-only; it finds the
repositories and their folders through GitService, so it never leaves the
project folder."""
from collections import Counter
from fnmatch import fnmatchcase
from pathlib import Path

from core.error import AppError, ValidationError
from core.observability import LogPrefix, observed
from domain.maven.pom import parse_pom
from models.domain.maven import MavenPom, PomAlignment, PomCheck, PomCheckKind, RepositoryPom
from service.git_service import GitService

_POM = "pom.xml"
_MAX_POM_BYTES = 2_000_000
_PREFERRED_PARENT_SUFFIX = "-parent-lib"
"""A recognised parent ending like this wins over one named more often: the
libraries' parent, which the microservices' parent may outnumber."""
_MODULE_DEPTH = 3
"""How deep inside a repository the modules' POMs are looked for (parent candidates)."""
_SKIPPED_FOLDERS = {"target", "build", "src", "node_modules", "dist", "out", "bin", "venv"}


class MavenService:

    def __init__(self, git: GitService):
        self._git = git

    @observed(LogPrefix.MAVEN_SERVICE)
    def root_poms(self, project_name: str) -> list[RepositoryPom]:
        """The root ``pom.xml`` of every repository of the project, in path
        order; one that is missing or unreadable says so, the others stay."""
        repositories = self._git.repositories(project_name)
        if not repositories:
            raise ValidationError("Nessun repository git nella cartella del progetto.")
        return [self._root_pom(project_name, repository.path) for repository in repositories]

    def parent_alignment(self, project_name: str, parent_artifact_id: str = "", property_pattern: str = "") -> PomAlignment:
        """Every root POM compared with the version of the parent POM.

        The parent is the POM whose ``artifactId`` is ``parent_artifact_id``:
        the root ``pom.xml`` of a repository or the one of a module inside it
        (a parent kept in a multi-module repository). ``""`` = recognised: the
        POM of the project that the most root POMs name as their ``<parent>``
        (ties: the first by name). A library is checked by its ``<parent>``
        version, a microservice by the properties matching
        ``property_pattern`` (a name, or a pattern with ``*``, e.g.
        ``*.libraries.version``; ``""`` = libraries only)."""
        parent_artifact_id, property_pattern = parent_artifact_id.strip(), property_pattern.strip()
        poms = self.root_poms(project_name)
        candidates = self._parent_candidates(project_name, poms)
        named = Counter(item.pom.parent.artifact_id for item in poms if item.pom and item.pom.parent and item.pom.parent.artifact_id)
        detected = not parent_artifact_id
        if detected:
            parent_artifact_id = _recognised_parent(poms, candidates)
        reference = candidates.get(parent_artifact_id) if parent_artifact_id else None
        alignment = PomAlignment(
            parent_artifact_id=parent_artifact_id,
            detected=detected,
            property_pattern=property_pattern,
            any_pom=any(item.pom or item.error for item in poms),
            reference_repository=reference[0] if reference else None,
            reference_pom=reference[1] if reference else "",
            reference_version=reference[2].version if reference else "",
            named_parents=dict(sorted(named.items(), key=lambda item: (-item[1], item[0]))),
        )
        for item in poms:
            if reference and item.repository == reference[0] and reference[1] == _POM:
                continue  # the parent itself
            if item.pom is None and item.error:
                alignment.unreadable.append(item)
                continue
            if item.pom is None:
                alignment.without_pom.append(item.repository)
                continue
            checks = []
            if parent_artifact_id and item.pom.parent and item.pom.parent.artifact_id == parent_artifact_id:
                checks.append((PomCheckKind.PARENT, "parent", item.pom.parent.version))
            if property_pattern:
                checks += [(PomCheckKind.PROPERTY, name, value) for name, value in sorted(item.pom.properties.items())
                           if fnmatchcase(name, property_pattern)]
            if not checks:
                if not (reference and item.repository == reference[0]):  # the aggregator holding the parent module
                    alignment.not_relevant.append(item.repository)
            alignment.checks += [
                PomCheck(repository=item.repository, kind=kind, name=name, value=value,
                         aligned=bool(alignment.reference_version) and value == alignment.reference_version)
                for kind, name, value in checks
            ]
        if property_pattern and not any(check.kind is PomCheckKind.PROPERTY for check in alignment.checks):
            alignment.version_properties = sorted({
                name for item in poms if item.pom for name in item.pom.properties if "version" in name.lower()
            })
        return alignment

    def _parent_candidates(self, project_name: str, poms: list[RepositoryPom]) -> dict[str, tuple[str, str, MavenPom]]:
        """artifactId → (repository, POM path in it, POM) of every POM that can
        be the parent: the root ones first, then the modules' (first found wins)."""
        candidates: dict[str, tuple[str, str, MavenPom]] = {}
        for item in poms:
            if item.pom and item.pom.artifact_id:
                candidates.setdefault(item.pom.artifact_id, (item.repository, _POM, item.pom))
        for item in poms:
            for path, pom in self._module_poms(project_name, item.repository):
                if pom.artifact_id:
                    candidates.setdefault(pom.artifact_id, (item.repository, path, pom))
        return candidates

    def _module_poms(self, project_name: str, repository: str) -> list[tuple[str, MavenPom]]:
        """The readable ``pom.xml`` of the modules of a repository, down to
        ``_MODULE_DEPTH`` folders, without build output, sources and hidden folders."""
        try:
            root = self._git.repository_folder(project_name, repository)
        except AppError:
            return []
        found: list[tuple[str, MavenPom]] = []

        def visit(folder: Path, depth: int) -> None:
            try:
                children = sorted(child for child in folder.iterdir() if child.is_dir())
            except OSError:
                return
            for child in children:
                if child.name.startswith(".") or child.name in _SKIPPED_FOLDERS:
                    continue
                file = child / _POM
                if file.is_file() and file.stat().st_size <= _MAX_POM_BYTES:
                    try:
                        found.append((file.relative_to(root).as_posix(), parse_pom(file.read_bytes())))
                    except (AppError, OSError):
                        pass
                if depth < _MODULE_DEPTH:
                    visit(child, depth + 1)

        visit(root, 1)
        return found

    def _root_pom(self, project_name: str, path: str) -> RepositoryPom:
        try:
            file = self._git.repository_folder(project_name, path) / _POM
            if not file.is_file():
                return RepositoryPom(repository=path)
            if file.stat().st_size > _MAX_POM_BYTES:
                return RepositoryPom(repository=path, error=f"{_POM} troppo grande (oltre {_MAX_POM_BYTES // 1_000_000} MB)")
            return RepositoryPom(repository=path, pom=parse_pom(file.read_bytes()))
        except (AppError, OSError) as exc:
            return RepositoryPom(repository=path, error=str(exc))


def _recognised_parent(poms: list[RepositoryPom], candidates: dict[str, tuple[str, str, MavenPom]]) -> str:
    """The ``artifactId`` of the project's POM (root or module) that the most
    root POMs name as ``<parent>``, preferring one that ends with
    ``_PREFERRED_PARENT_SUFFIX``; ``""`` when no POM of the project is the
    parent of another."""
    named = Counter(
        item.pom.parent.artifact_id for item in poms
        if item.pom and item.pom.parent and item.pom.parent.artifact_id in candidates
        and candidates[item.pom.parent.artifact_id][0] != item.repository
    )
    if not named:
        return ""
    preferred = [artifact for artifact in named if artifact.endswith(_PREFERRED_PARENT_SUFFIX)]
    return min(preferred or named, key=lambda artifact: (-named[artifact], artifact))
