"""Maven on a project's repositories: their root ``pom.xml`` read from the
working tree (the branch each repository is on, uncommitted changes
included) and compared with a parent POM. Read-only; it finds the
repositories and their folders through GitService, so it never leaves the
project folder."""
from core.error import AppError, ValidationError
from core.observability import LogPrefix, observed
from domain.maven.pom import parse_pom
from models.domain.maven import PomAlignment, PomCheck, PomCheckKind, RepositoryPom
from service.git_service import GitService

_POM = "pom.xml"
_MAX_POM_BYTES = 2_000_000


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

    def parent_alignment(self, project_name: str, parent_artifact_id: str, property_name: str = "") -> PomAlignment:
        """Every root POM compared with the version of the parent POM (the
        repository whose ``artifactId`` is ``parent_artifact_id``): a library
        by its ``<parent>`` version, a microservice by ``property_name`` in
        its ``<properties>`` (``""`` = libraries only)."""
        parent_artifact_id, property_name = parent_artifact_id.strip(), property_name.strip()
        if not parent_artifact_id:
            raise ValidationError("Indica l'artifactId del parent con cui confrontare i POM.")
        poms = self.root_poms(project_name)
        reference = next((item for item in poms if item.pom and item.pom.artifact_id == parent_artifact_id), None)
        alignment = PomAlignment(
            parent_artifact_id=parent_artifact_id,
            property_name=property_name,
            reference_repository=reference.repository if reference else None,
            reference_version=reference.pom.version if reference and reference.pom else "",
        )
        for item in poms:
            if item is reference:
                continue
            if item.pom is None and item.error:
                alignment.unreadable.append(item)
                continue
            if item.pom is None:
                alignment.without_pom.append(item.repository)
                continue
            checks = []
            if item.pom.parent and item.pom.parent.artifact_id == parent_artifact_id:
                checks.append((PomCheckKind.PARENT, item.pom.parent.version))
            if property_name and property_name in item.pom.properties:
                checks.append((PomCheckKind.PROPERTY, item.pom.properties[property_name]))
            if not checks:
                alignment.not_relevant.append(item.repository)
            alignment.checks += [
                PomCheck(repository=item.repository, kind=kind, value=value,
                         aligned=bool(alignment.reference_version) and value == alignment.reference_version)
                for kind, value in checks
            ]
        return alignment

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
