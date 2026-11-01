"""Reading a JaCoCo XML report (``target/site/jacoco/jacoco.xml``): no I/O,
the bytes in, the line coverage of every source file out.

A ``<sourcefile>`` inside a ``<package>`` gives ``<line nr mi ci mb cb>``: a
line is covered when at least one of its instructions ran (``ci > 0``).
Lines JaCoCo does not list are not executable (comments, imports, blank).
The DOCTYPE the report declares is never fetched (standard library parser)."""
import xml.etree.ElementTree as ElementTree

from core.error import ValidationError

LineCoverage = dict[str, dict[int, bool]]
"""``<package>/<File>.java`` (as under ``src/main/java``) → line number → covered."""


def parse_jacoco(data: bytes | str) -> LineCoverage:
    """ValidationError when it is not XML or not a JaCoCo ``<report>``."""
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise ValidationError(f"jacoco.xml non valido: {exc}") from exc
    if root.tag != "report":
        raise ValidationError(f"jacoco.xml non valido: la radice è <{root.tag}>, non <report>.")
    coverage: LineCoverage = {}
    for package in root.iter("package"):
        prefix = package.get("name", "").strip("/")
        for source in package.findall("sourcefile"):
            path = f"{prefix}/{source.get('name', '')}" if prefix else source.get("name", "")
            lines = coverage.setdefault(path, {})
            for line in source.findall("line"):
                try:
                    number, covered = int(line.get("nr", "")), int(line.get("ci", "0")) > 0
                except ValueError:
                    continue
                lines[number] = lines.get(number, False) or covered
    return coverage
