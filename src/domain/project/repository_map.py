"""The map of a project's repositories, written into the context
document ``context/repository.md`` with no LLM: per repository its build
tool and commands, what it uses of the others (Maven artifacts, npm
packages, Python distributions of the project) and its branches, plus the
build order (libraries before who uses them). Pure functions: the service
reads the files and git.

Only the part between ``START`` and ``END`` is the app's: generating the
map again rewrites it and keeps what the user wrote around it."""
import json
import re
import tomllib
from dataclasses import dataclass, field
from datetime import datetime
from xml.etree import ElementTree

from models.domain.dev import TestKind

DOCUMENT = "repository.md"
START = "<!-- mappa dei repository: inizio (generata dall'app, rigenerarla riscrive solo questa parte) -->"
END = "<!-- mappa dei repository: fine -->"
HEADER = ("# Repository\n\nLa mappa dei repository del progetto: build, dipendenze tra repository, branch. "
          "Scrivi le tue note fuori dalla parte generata.")
MAIN_BRANCHES = ("main", "master", "develop")
KIND_LABELS = {TestKind.MAVEN: "Maven", TestKind.NODE: "Node (npm)", TestKind.PYTHON: "Python", TestKind.UNKNOWN: "non riconosciuto"}
_PEP508_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


@dataclass
class RepositoryInfo:
    path: str
    kind: TestKind
    build: str = ""
    test: str = ""
    name: str = ""
    """What the others use to depend on it (artifactId, package or distribution name)."""
    dependencies: list[str] = field(default_factory=list)
    """Everything it depends on (names); the map keeps the project's."""
    current: str | None = None
    branches: list[str] = field(default_factory=list)


def identity(kind: TestKind, text: str) -> tuple[str, list[str]]:
    """The name and the dependencies' names from the build file (``pom.xml``, ``package.json``, ``pyproject.toml``)."""
    try:
        if kind is TestKind.MAVEN:
            root = ElementTree.fromstring(text)
            for element in root.iter():
                element.tag = element.tag.split("}", 1)[-1]
            name = root.findtext("artifactId", "").strip()
            dependencies = [item.findtext("artifactId", "").strip() for item in root.iter("dependency")]
            parent = root.findtext("parent/artifactId", "").strip()
            return name, [item for item in [parent, *dependencies] if item]
        if kind is TestKind.NODE:
            data = json.loads(text)
            return str(data.get("name", "")), [*data.get("dependencies", {}), *data.get("devDependencies", {})]
        if kind is TestKind.PYTHON:
            project = tomllib.loads(text).get("project", {})
            names = [match.group(1) for item in project.get("dependencies", []) if (match := _PEP508_NAME.match(item))]
            return str(project.get("name", "")), names
    except (ElementTree.ParseError, ValueError, tomllib.TOMLDecodeError, AttributeError, TypeError):
        pass
    return "", []


def main_branches(local: list[str], remote: list[str]) -> list[str]:
    """``main``, ``master``, ``develop`` among the local and remote branches, in that order."""
    names = set(local) | {branch.split("/", 1)[-1] for branch in remote}
    return [name for name in MAIN_BRANCHES if name in names]


def render(repositories: list[RepositoryInfo], when: datetime) -> str:
    """The generated part (between the markers)."""
    by_name = {info.name.lower(): info for info in repositories if info.name}
    uses = {info.path: sorted({by_name[dep.lower()].path for dep in info.dependencies if dep.lower() in by_name} - {info.path})
            for info in repositories}
    lines = [START, f"_Generata il {when:%d/%m/%Y %H:%M}._", ""]
    for info in repositories:
        label = info.path or "(cartella del progetto)"
        build = [KIND_LABELS[info.kind]] + ([f"build `{info.build}`"] if info.build else []) + ([f"test `{info.test}`"] if info.test else [])
        used_by = sorted(path or "(cartella del progetto)" for path, deps in uses.items() if info.path in deps)
        branches = f"corrente {info.current}" if info.current else "HEAD staccato"
        lines += [f"## {label}", f"- Build: {' · '.join(build)}"]
        lines += [f"- Nome: {info.name}"] if info.name else []
        lines += [f"- Usa: {', '.join(path or '(cartella del progetto)' for path in uses[info.path]) or 'nessun repository del progetto'}",
                  f"- Usato da: {', '.join(used_by) or 'nessun repository del progetto'}",
                  f"- Branch: {branches}" + (f" · principali: {', '.join(info.branches)}" if info.branches else ""), ""]
    lines += ["## Ordine di build", "Prima chi è usato, poi chi lo usa:"]
    lines += [f"{number}. {path or '(cartella del progetto)'}" for number, path in enumerate(build_order(uses), 1)]
    return "\n".join([*lines, END])


def build_order(uses: dict[str, list[str]]) -> list[str]:
    """The repositories, each after the ones it uses (a cycle keeps the remaining ones in their order)."""
    order: list[str] = []
    left = list(uses)
    while left:
        ready = [path for path in left if all(dep in order for dep in uses[path])] or left[:1]
        order += ready
        left = [path for path in left if path not in ready]
    return order


def merge(document: str, generated: str) -> str:
    """``generated`` in place of the old generated part; a document without it gets it after its text (a new one, the header)."""
    text = document.strip()
    if START in text and END in text.split(START, 1)[1]:
        before, rest = text.split(START, 1)
        after = rest.split(END, 1)[1]
        return f"{before}{generated}{after}".strip() + "\n"
    return f"{text or HEADER}\n\n{generated}\n"
