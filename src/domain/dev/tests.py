"""The tests of a repository for the «Verifica sviluppo»: which tool (from the
files at its root), the default command, the tests «touched» by a change and
the failures read back from the output. Pure functions: no filesystem, no
processes (function/list/run_tests.py runs them).

- **Maven** (``pom.xml``): ``mvn -B test`` (``./mvnw`` when the repository has
  it); touched tests as ``-Dtest=FooTest,BarTest`` (surefire, without failing
  when one is not found).
- **Python** (``pyproject.toml``, ``setup.py``, ``pytest.ini``): ``uv run
  pytest`` (``pytest`` without ``uv.lock``); touched tests as file paths.
- **Node** (``package.json``): ``npm test``; touched tests as file paths after ``--``.

A test is «touched» when its own file changed, or when it is the test of a
changed source file: ``FooTest``/``FooTests``/``FooIT`` for ``Foo.java``,
``test_foo.py``/``foo_test.py`` for ``foo.py``, ``foo.test.ts``/``foo.spec.ts``
(any js/ts extension) for ``foo.ts``."""
import os
import re
import shlex
from pathlib import PurePosixPath

from models.domain.dev import TestKind, TestScope

SCOPE_LABELS = {TestScope.ALL: "tutti", TestScope.TOUCHED: "solo toccati"}

_PYTHON_MARKERS = ("pyproject.toml", "setup.py", "setup.cfg", "pytest.ini")
_JS = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")
_JAVA_TEST_SUFFIXES = ("Test", "Tests", "IT")
_MAX_FAILURE_LINES = 40
_TAIL_LINES = 25


def detect(root_files: set[str]) -> TestKind:
    """The tool, from the names of the files at the repository's root."""
    if "pom.xml" in root_files:
        return TestKind.MAVEN
    if any(marker in root_files for marker in _PYTHON_MARKERS):
        return TestKind.PYTHON
    if "package.json" in root_files:
        return TestKind.NODE
    return TestKind.UNKNOWN


def default_command(kind: TestKind, root_files: set[str], windows: bool = os.name == "nt") -> str:
    """``""`` when the tool is unknown: the user writes it in the settings.
    On Windows the Maven wrapper is ``mvnw.cmd``."""
    if kind is TestKind.MAVEN:
        if windows:
            return "mvnw.cmd -B test" if "mvnw.cmd" in root_files else "mvn -B test"
        return "./mvnw -B test" if "mvnw" in root_files else "mvn -B test"
    if kind is TestKind.PYTHON:
        return "uv run pytest" if "uv.lock" in root_files else "pytest"
    if kind is TestKind.NODE:
        return "npm test"
    return ""


def install_command(kind: TestKind, root_files: set[str], windows: bool = os.name == "nt") -> str:
    """The clean install of a repository, offered as an allowed command of the
    Operator (plan 11); ``""`` when the tool is unknown."""
    if kind is TestKind.MAVEN:
        return default_command(kind, root_files, windows).replace(" test", " clean install")
    if kind is TestKind.PYTHON:
        return "uv sync" if "uv.lock" in root_files else ""
    if kind is TestKind.NODE:
        return "npm ci" if "package-lock.json" in root_files else "npm install"
    return ""


def is_test_file(kind: TestKind, path: str) -> bool:
    name = PurePosixPath(path).name
    if kind is TestKind.MAVEN:
        return path.endswith(".java") and "/src/test/" in f"/{path}" and PurePosixPath(path).stem.endswith(_JAVA_TEST_SUFFIXES)
    if kind is TestKind.PYTHON:
        return name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py"))
    if kind is TestKind.NODE:
        return any(name.endswith(f".{marker}{extension}") for marker in ("test", "spec") for extension in _JS)
    return False


def touched_tests(kind: TestKind, changed: list[str], files: list[str]) -> list[str]:
    """The tests of ``changed`` among the repository's ``files`` (paths
    relative to its root, ``/`` separators), in ``files`` order: Maven test
    class names, file paths otherwise. Empty when the tool is unknown."""
    tests = [path for path in files if is_test_file(kind, path)]
    wanted = {path for path in changed if is_test_file(kind, path)}
    for path in changed:
        if not is_test_file(kind, path):
            wanted |= {test for test in tests if _tests_source(kind, test, path)}
    chosen = [test for test in tests if test in wanted]
    if kind is TestKind.MAVEN:
        return list(dict.fromkeys(PurePosixPath(test).stem for test in chosen))
    return chosen


def _tests_source(kind: TestKind, test: str, source: str) -> bool:
    test_path, source_path = PurePosixPath(test), PurePosixPath(source)
    if kind is TestKind.MAVEN:
        return source.endswith(".java") and test_path.stem in {source_path.stem + suffix for suffix in _JAVA_TEST_SUFFIXES}
    if kind is TestKind.PYTHON:
        return source.endswith(".py") and test_path.name in {f"test_{source_path.name}", f"{source_path.stem}_test.py"}
    if kind is TestKind.NODE:
        if source_path.suffix not in _JS:
            return False
        return any(test_path.name == f"{source_path.stem}.{marker}{extension}" for marker in ("test", "spec") for extension in _JS)
    return False


def command(base: str, kind: TestKind, selectors: list[str], windows: bool = os.name == "nt") -> list[str]:
    """``base`` (a shell-like command) as arguments, narrowed to ``selectors``
    (none = every test). ValueError for a command that does not parse. On
    Windows backslashes are path separators, not escapes: only the quotes
    around an argument are taken away."""
    arguments = split(base, windows)
    if not selectors:
        return arguments
    if kind is TestKind.MAVEN:
        return [*arguments, f"-Dtest={','.join(selectors)}", "-Dsurefire.failIfNoSpecifiedTests=false"]
    if kind is TestKind.NODE:
        return [*arguments, *([] if "--" in arguments else ["--"]), *selectors]
    return [*arguments, *selectors]


def split(text: str, windows: bool = os.name == "nt") -> list[str]:
    if not windows:
        return shlex.split(text)
    lexer = shlex.shlex(text, posix=False)
    lexer.whitespace_split = True
    return [part[1:-1] if len(part) > 1 and part[0] == part[-1] and part[0] in "\"'" else part for part in lexer]


_FAILURE_PATTERNS = {
    TestKind.PYTHON: re.compile(r"^(FAILED |ERROR |E\s{2,}|\S+\.py:\d+: )"),
    TestKind.MAVEN: re.compile(r"^\[ERROR\]\s+(?!(To see|Re-run|Failed to execute|-> \[Help|$))"),
    TestKind.NODE: re.compile(r"^\s*(●|FAIL\s|×|✕|AssertionError|Error:|expected )"),
}


def failures(kind: TestKind, output: str) -> list[str]:
    """The lines that say what failed (pytest, surefire, jest/vitest), at
    most 40; the last lines of the output when nothing matches."""
    lines = [line.rstrip() for line in output.splitlines()]
    pattern = _FAILURE_PATTERNS.get(kind)
    found = [line for line in lines if pattern and pattern.match(line)] if pattern else []
    if not found:
        found = [line for line in lines if line.strip()][-_TAIL_LINES:]
    if len(found) > _MAX_FAILURE_LINES:
        return [*found[:_MAX_FAILURE_LINES], f"… e altre {len(found) - _MAX_FAILURE_LINES} righe"]
    return found
