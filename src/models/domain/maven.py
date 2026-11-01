"""Maven domain models: what is read from a ``pom.xml`` and the alignment of
the project's repositories to a parent POM."""
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
    reference_version: str = ""
    checks: list[PomCheck] = []
    unreadable: list[RepositoryPom] = []
    without_pom: MaskRepositoryNames = []
    not_relevant: MaskRepositoryNames = []
    """With a POM but neither the parent nor the property."""
