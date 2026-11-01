"""Maven on a project's repositories: their root ``pom.xml`` read from the
working tree (the branch each repository is on, uncommitted changes
included) and compared with a parent POM, and the JaCoCo coverage of the
lines not pushed yet. It finds the repositories and their folders through
GitService, so it never leaves the project folder. The only thing it writes
is the JaCoCo XML report under ``target/`` (``mvn jacoco:report``), and only
in a repository confirmed on the parent's version."""
from collections import Counter
from fnmatch import fnmatchcase
from pathlib import Path

from core.error import AppError, ValidationError
from core.observability import LogPrefix, observed
from domain.client.maven.client import MavenClient
from domain.maven.jacoco import LineCoverage, parse_jacoco
from domain.maven.pom import parse_pom
from models.domain.maven import (
    CoverageCheck,
    CoverageStatus,
    MavenPom,
    NewCodeCoverage,
    PomAlignment,
    PomCheck,
    PomCheckKind,
    RepositoryPom,
    UncoveredFile,
)
from service.git_service import GitService

_POM = "pom.xml"
_MAX_POM_BYTES = 2_000_000
_PREFERRED_PARENT_SUFFIX = "-parent-lib"
"""A recognised parent ending like this wins over one named more often: the
libraries' parent, which the microservices' parent may outnumber."""
_MODULE_DEPTH = 3
"""How deep inside a repository the modules' POMs are looked for (parent candidates)."""
_SKIPPED_FOLDERS = {"target", "build", "src", "node_modules", "dist", "out", "bin", "venv"}
_JACOCO_EXEC = "target/jacoco.exec"
_JACOCO_XML = "target/site/jacoco/jacoco.xml"
_MAIN_JAVA = "src/main/java/"


class MavenService:

    def __init__(self, git: GitService, maven: MavenClient | None = None):
        self._git = git
        self._maven = maven or MavenClient()

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

    @observed(LogPrefix.MAVEN_SERVICE)
    def new_code_coverage(
        self, project_name: str, repository: str | None = None, threshold: int = 80,
        parent_artifact_id: str = "", property_pattern: str = "",
    ) -> NewCodeCoverage:
        """The JaCoCo coverage of the lines of ``src/main/java`` that the
        commits not pushed yet add, for every repository with a root POM
        (``repository`` = only that one).

        JaCoCo comes from the parent POM, so first the alignment
        (``parent_alignment`` with the same arguments): a repository not on
        the parent's version, or whose alignment cannot be confirmed, is
        skipped and ``mvn`` never runs there. In the others, when a module's
        ``jacoco.exec`` is newer than its XML (or the XML is missing),
        ``mvn jacoco:report`` writes it (the tests are not run)."""
        if not 1 <= threshold <= 100:
            raise ValidationError("La soglia di coverage deve essere tra 1 e 100.")
        alignment = self.parent_alignment(project_name, parent_artifact_id, property_pattern)
        result = NewCodeCoverage(
            threshold=threshold, any_pom=alignment.any_pom, parent_artifact_id=alignment.parent_artifact_id,
            reference_version=alignment.reference_version, without_pom=alignment.without_pom,
        )
        gates = _gates(alignment)
        if repository is not None:
            repository = repository.strip().strip("/\\")
            if repository in alignment.without_pom:
                result.any_pom, result.without_pom = False, [repository]
                return result
            if repository not in gates:
                raise ValidationError(f"{repository or 'progetto'}: non è un repository del progetto.")
            gates = {repository: gates[repository]}
            result.without_pom = []
        for name, gate in sorted(gates.items(), key=lambda item: item[0].lower()):
            result.checks.append(gate or self._measure(project_name, name, threshold))
        return result

    def _measure(self, project_name: str, repository: str, threshold: int) -> CoverageCheck:
        try:
            changes = self._git.unpushed_changes(project_name, repository, "*.java")
            root = self._git.repository_folder(project_name, repository)
        except AppError as exc:
            return CoverageCheck(repository=repository, status=CoverageStatus.UNREADABLE, reason=str(exc))
        check = CoverageCheck(repository=repository, status=CoverageStatus.NOTHING_TO_MEASURE, unpushed=changes.commits)
        if not changes.commits:
            check.status = CoverageStatus.NOTHING_TO_PUSH
            return check
        by_module: dict[str, dict[str, tuple[str, list[int]]]] = {}
        for path, lines in changes.added_lines.items():
            if split := _main_source(path):
                module, source = split
                by_module.setdefault(module, {})[source] = (path, lines)
        if not by_module:
            check.reason = f"nessuna riga di {_MAIN_JAVA} nei commit da pushare"
            return check
        reports = self._reports(root, list(by_module), changes.head_timestamp, check)
        if reports is None:
            return check
        uncovered: list[UncoveredFile] = []
        for module, sources in sorted(by_module.items()):
            for source, (path, lines) in sorted(sources.items()):
                known = reports.get(module, {}).get(source)
                if known is None:
                    check.not_measured.append(path)
                    continue
                measured = [line for line in lines if line in known]
                check.total += len(measured)
                check.covered += sum(1 for line in measured if known[line])
                if missed := [line for line in measured if not known[line]]:
                    uncovered.append(UncoveredFile(path=path, lines=missed))
        check.uncovered = uncovered
        if not check.total:
            if check.not_measured:
                check.status, check.reason = CoverageStatus.NO_REPORT, "il report JaCoCo non contiene i file cambiati (rilancia i test)"
            else:
                check.reason = "nessuna riga eseguibile nei commit da pushare"
            return check
        check.status = CoverageStatus.BELOW if check.percent < threshold else CoverageStatus.ABOVE
        return check

    def _reports(self, root: Path, modules: list[str], head_timestamp: float, check: CoverageCheck) -> dict[str, LineCoverage] | None:
        """The JaCoCo line coverage of the ``modules`` (``""`` = the repository
        root, else ``"<module>/"``) that have a report, after writing the XML
        that is missing or older than its ``jacoco.exec``; None (and ``check``
        says why) when no module has one."""
        execs = {module: root / module / _JACOCO_EXEC for module in modules}
        xmls = {module: root / module / _JACOCO_XML for module in modules}
        present = {module: file for module, file in execs.items() if file.is_file()}
        if not present and not any(file.is_file() for file in xmls.values()):
            check.status, check.reason = CoverageStatus.NO_REPORT, f"nessun {_JACOCO_EXEC}: lancia prima i test (mvn verify)"
            return None
        check.stale = any(file.stat().st_mtime < head_timestamp for file in present.values())
        if any(not xmls[module].is_file() or xmls[module].stat().st_mtime < file.stat().st_mtime for module, file in present.items()):
            try:
                self._maven.jacoco_report(root)
            except AppError as exc:
                check.status, check.reason = CoverageStatus.NO_REPORT, str(exc)
                return None
            check.report_generated = True
        reports: dict[str, LineCoverage] = {}
        errors: list[str] = []
        for module, file in xmls.items():
            if file.is_file():
                try:
                    reports[module] = parse_jacoco(file.read_bytes())
                except (AppError, OSError) as exc:
                    errors.append(f"{module}{_JACOCO_XML}: {exc}")
        if not reports:
            check.status = CoverageStatus.NO_REPORT
            check.reason = "; ".join(errors) or f"mvn jacoco:report non ha scritto {_JACOCO_XML}"
            return None
        return reports

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


def _gates(alignment: PomAlignment) -> dict[str, CoverageCheck | None]:
    """Every repository with a root POM → None when confirmed on the parent's
    version (JaCoCo can run), else the skipped check saying why."""
    checks: dict[str, list[PomCheck]] = {}
    for check in alignment.checks:
        checks.setdefault(check.repository, []).append(check)
    gates: dict[str, CoverageCheck | None] = {}
    if not alignment.reference_version:
        if not alignment.parent_artifact_id:
            reason = "nessun parent riconosciuto nel progetto"
        elif alignment.reference_repository is None:
            reason = f"nessun repository del progetto ha artifactId {alignment.parent_artifact_id}"
        else:
            reason = f"il parent {alignment.parent_artifact_id} non ha una version"
        names = [*checks, *alignment.not_relevant, *(item.repository for item in alignment.unreadable)]
        if alignment.reference_repository is not None:
            names.append(alignment.reference_repository)
        return {name: CoverageCheck(repository=name, status=CoverageStatus.NOT_VERIFIABLE, reason=reason) for name in names}
    for name, items in checks.items():
        wrong = [item for item in items if not item.aligned]
        gates[name] = None if not wrong else CoverageCheck(
            repository=name, status=CoverageStatus.NOT_ALIGNED,
            reason="; ".join(f"{item.name}: {item.value}{' (non risolto)' if '${' in item.value else ''} → {alignment.reference_version}"
                             for item in wrong),
        )
    expected = f"il pom.xml non ha come <parent> {alignment.parent_artifact_id}" + (
        f" né la proprietà {alignment.property_pattern}" if alignment.property_pattern else " (nessuna proprietà indicata per i microservizi)"
    )
    for name in alignment.not_relevant:
        gates.setdefault(name, CoverageCheck(repository=name, status=CoverageStatus.NOT_VERIFIABLE, reason=expected))
    for item in alignment.unreadable:
        gates[item.repository] = CoverageCheck(repository=item.repository, status=CoverageStatus.NOT_VERIFIABLE,
                                               reason=f"pom.xml non letto: {item.error}")
    if alignment.reference_repository is not None:
        gates.setdefault(alignment.reference_repository, None)  # the parent itself
    return gates


def _main_source(path: str) -> tuple[str, str] | None:
    """``<module>/src/main/java/<package path>/<File>.java`` → (``"<module>/"``
    or ``""``, ``"<package path>/<File>.java"``); None for tests and the rest."""
    index = path.find(_MAIN_JAVA)
    while index > 0 and path[index - 1] != "/":
        index = path.find(_MAIN_JAVA, index + 1)
    if index < 0 or not path.endswith(".java"):
        return None
    return path[:index], path[index + len(_MAIN_JAVA):]
