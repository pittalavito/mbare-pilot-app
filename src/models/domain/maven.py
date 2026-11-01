"""Maven domain models: what is read from a ``pom.xml``, the alignment of
the project's repositories to a parent POM and the JaCoCo coverage of the
code not pushed yet."""
from enum import StrEnum

from pydantic import BaseModel

from models.domain.masking import MaskRepositoryName, MaskRepositoryNames


class MavenParent(BaseModel):
    group_id: str = ""
    artifact_id: str = ""
    version: str = ""


class MavenPom(BaseModel):
    """The fields of a ``pom.xml`` the reports use, with ``${...}`` resolved
    where the POM itself (or its parent's version) says what they are."""
    group_id: str = ""
    """Inherited from the parent when the POM does not declare it."""
    artifact_id: str = ""
    version: str = ""
    """Inherited from the parent when the POM does not declare it."""
    parent: MavenParent | None = None
    properties: dict[str, str] = {}


class RepositoryPom(BaseModel):
    """The root ``pom.xml`` of a repository of the project."""
    repository: MaskRepositoryName
    pom: MavenPom | None = None
    """None when the repository has no ``pom.xml`` or it could not be read."""
    error: str = ""
    """Why it could not be read; empty when it has no ``pom.xml`` at all."""


class PomCheckKind(StrEnum):
    PARENT = "parent"
    """A library: its ``<parent>`` is the reference POM."""
    PROPERTY = "property"
    """A microservice: it declares the property with the libraries' version."""


class PomCheck(BaseModel):
    """One value compared with the reference version."""
    repository: MaskRepositoryName
    kind: PomCheckKind
    name: str
    """``parent``, or the property's name."""
    value: str
    aligned: bool
    """False also when the value is not resolved (``${...}``)."""


class PomAlignment(BaseModel):
    """Every root POM of the project compared with the version of a parent POM."""
    parent_artifact_id: str
    """The one asked for, or the one recognised; ``""`` = none recognised."""
    detected: bool = False
    """The parent was not given: it is the project's repository the others name as ``<parent>``."""
    property_pattern: str = ""
    any_pom: bool = False
    """At least one repository has a ``pom.xml`` (readable or not)."""
    reference_repository: MaskRepositoryName | None = None
    """The repository whose POM is the parent; None when the project has none."""
    reference_pom: str = ""
    """That POM, relative to its repository: ``pom.xml``, or a module's (``parent-lib/pom.xml``)."""
    reference_version: str = ""
    checks: list[PomCheck] = []
    unreadable: list[RepositoryPom] = []
    without_pom: MaskRepositoryNames = []
    not_relevant: MaskRepositoryNames = []
    """With a POM but neither the parent nor the property."""
    named_parents: dict[str, int] = {}
    """The ``<parent>`` artifactIds of the root POMs, with how many name each:
    to say what was seen when no reference is found."""
    version_properties: list[str] = []
    """The properties with ``version`` in their name, when ``property_pattern``
    matched none: to show which names the POMs really use."""


class CoverageStatus(StrEnum):
    """The outcome of the new-code coverage of one repository."""
    BELOW = "below"
    """Measured, under the threshold."""
    ABOVE = "above"
    """Measured, at or over the threshold."""
    NO_REPORT = "no_report"
    """Lines to measure, but no usable JaCoCo report (no ``jacoco.exec``, ``mvn`` failed, files not in it)."""
    NOTHING_TO_PUSH = "nothing_to_push"
    NOTHING_TO_MEASURE = "nothing_to_measure"
    """Commits to push, but no executable line of ``src/main/java`` in them."""
    NOT_ALIGNED = "not_aligned"
    """Skipped: not on the parent's version (JaCoCo comes from the parent): ``mvn`` never runs."""
    NOT_VERIFIABLE = "not_verifiable"
    """Skipped: the alignment to the parent cannot be confirmed: ``mvn`` never runs."""
    UNREADABLE = "unreadable"
    """Git could not say what is not pushed."""


class UncoveredFile(BaseModel):
    path: str
    """Relative to the repository."""
    lines: list[int]
    """The new executable lines JaCoCo saw not covered, ascending."""


class CoverageCheck(BaseModel):
    """The coverage of the lines a repository has not pushed yet."""
    repository: MaskRepositoryName
    status: CoverageStatus
    reason: str = ""
    """Why it was skipped or has no report; the misalignment for NOT_ALIGNED."""
    unpushed: int = 0
    """Commits of HEAD that no remote branch has."""
    covered: int = 0
    total: int = 0
    """New executable lines JaCoCo knows (covered + not covered)."""
    uncovered: list[UncoveredFile] = []
    not_measured: list[str] = []
    """Changed files of ``src/main/java`` that the report does not know (excluded, or a module without ``jacoco.exec``)."""
    stale: bool = False
    """A ``jacoco.exec`` is older than the last commit: the tests ran before it."""
    report_generated: bool = False
    """``mvn jacoco:report`` ran to write the XML."""

    @property
    def percent(self) -> float:
        return 100.0 * self.covered / self.total if self.total else 100.0


class NewCodeCoverage(BaseModel):
    """The new-code coverage of the project's repositories, after their alignment to the parent."""
    threshold: int
    any_pom: bool = False
    parent_artifact_id: str = ""
    reference_version: str = ""
    checks: list[CoverageCheck] = []
    without_pom: MaskRepositoryNames = []
