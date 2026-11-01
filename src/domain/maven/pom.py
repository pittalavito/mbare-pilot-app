"""Reading a ``pom.xml``: no I/O, the text in, a MavenPom out.

Maven's namespace is ignored (POMs come with and without it). ``${name}`` in
the values is resolved with the POM's own ``<properties>``, ``project.version``
and ``project.parent.version``, a few levels deep (a property may point to
another). What the POM cannot say (a property of a remote parent) stays as it
is, ``${...}`` included, so a report can show it is not resolved.

The standard library's parser never fetches external entities, and the
expat bundled with Python 3.12 refuses entity-expansion bombs."""
import re
import xml.etree.ElementTree as ElementTree

from core.error import ValidationError
from models.domain.maven import MavenParent, MavenPom

_PLACEHOLDER = re.compile(r"\$\{([^}]+)\}")
_MAX_DEPTH = 10


def parse_pom(text: bytes | str) -> MavenPom:
    """``text`` as bytes keeps the encoding the file declares. ValidationError
    when it is not XML or its root is not ``<project>``."""
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        raise ValidationError(f"pom.xml non valido: {exc}") from exc
    if _local(root.tag) != "project":
        raise ValidationError(f"pom.xml non valido: la radice è <{_local(root.tag)}>, non <project>.")
    parent_node = _child(root, "parent")
    parent = None if parent_node is None else MavenParent(
        group_id=_text(parent_node, "groupId"), artifact_id=_text(parent_node, "artifactId"), version=_text(parent_node, "version"),
    )
    properties_node = _child(root, "properties")
    raw_properties = {} if properties_node is None else {
        _local(item.tag): (item.text or "").strip() for item in properties_node if isinstance(item.tag, str)
    }
    version = _text(root, "version") or (parent.version if parent else "")
    known = {**raw_properties, "project.version": version, "version": version}
    if parent:
        known["project.parent.version"] = parent.version
    resolved = {name: _resolve(value, known) for name, value in known.items()}
    if parent:
        parent.version = _resolve(parent.version, resolved)
    return MavenPom(
        group_id=_text(root, "groupId") or (parent.group_id if parent else ""),
        artifact_id=_text(root, "artifactId"),
        version=_resolve(version, resolved),
        parent=parent,
        properties={name: resolved[name] for name in raw_properties},
    )


def _resolve(value: str, known: dict[str, str]) -> str:
    for _ in range(_MAX_DEPTH):
        replaced = _PLACEHOLDER.sub(lambda match: known.get(match.group(1), match.group(0)), value)
        if replaced == value:
            return value
        value = replaced
    return value


def _local(tag: str) -> str:
    """``{http://maven.apache.org/POM/4.0.0}version`` → ``version``."""
    return tag.rsplit("}", 1)[-1]


def _child(node: ElementTree.Element, name: str) -> ElementTree.Element | None:
    return next((item for item in node if isinstance(item.tag, str) and _local(item.tag) == name), None)


def _text(node: ElementTree.Element, name: str) -> str:
    child = _child(node, name)
    return (child.text or "").strip() if child is not None else ""
