"""JaCoCo coverage of the code not pushed yet: the report parser
(domain/maven/jacoco.py), the lines git says are not pushed (GitClient,
GitService), the Maven client, MavenService.new_code_coverage with its gate
on the parent alignment, and the function coverage_new_code. On real git
repositories in a tmp dir (needs ``git`` on PATH); Maven is a fake."""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from core.error import UpstreamError, ValidationError
from domain.client.git.client import GitClient
from domain.client.maven.client import MavenClient
from domain.maven.jacoco import parse_jacoco
from function.context import FunctionContext
from function.list import coverage_new_code
from function.registry import FUNCTION_REGISTRY
from models.domain.maven import CoverageStatus
from models.domain.project import Project, ProjectSource
from service.maven_service import MavenService

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
NS = 'xmlns="http://maven.apache.org/POM/4.0.0"'
PKG = "src/main/java/net/acme"


def _jacoco(files: dict[str, dict[int, int]], package: str = "net/acme") -> str:
    """A JaCoCo report: file name → line number → covered instructions (0 = missed)."""
    sources = "".join(
        f'<sourcefile name="{name}">' + "".join(f'<line nr="{nr}" mi="{0 if ci else 2}" ci="{ci}" mb="0" cb="0"/>' for nr, ci in lines.items())
        + "</sourcefile>" for name, lines in files.items()
    )
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<!DOCTYPE report PUBLIC "-//JACOCO//DTD Report 1.1//EN" "report.dtd">'
            f'<report name="x"><package name="{package}"><class name="{package}/A"/>{sources}</package></report>')


# ------------------------------------------------------------------ parsing

def test_parse_jacoco_lines_by_source_path():
    coverage = parse_jacoco(_jacoco({"Orders.java": {3: 1, 4: 0}, "Util.java": {9: 2}}).encode())

    assert coverage == {"net/acme/Orders.java": {3: True, 4: False}, "net/acme/Util.java": {9: True}}


def test_parse_jacoco_default_package_and_odd_lines():
    text = ('<report name="x"><package name=""><sourcefile name="Main.java">'
            '<line nr="1" ci="0"/><line nr="1" ci="3"/><line nr="x" ci="1"/></sourcefile></package></report>')

    assert parse_jacoco(text) == {"Main.java": {1: True}}


@pytest.mark.parametrize("text, message", [("non xml", "jacoco.xml non valido"), ("<project/>", "non <report>")])
def test_parse_jacoco_invalid(text, message):
    with pytest.raises(ValidationError, match=message):
        parse_jacoco(text)


# ------------------------------------------------------------- maven client

def _script(folder: Path, body: str) -> str:
    script = folder / "fake-mvn"
    script.write_text(f"#!{sys.executable}\nimport sys, pathlib\n{body}\n", encoding="utf-8")
    script.chmod(0o755)
    return str(script)


@pytest.mark.skipif(os.name == "nt", reason="shell script as mvn")
def test_maven_client_runs_jacoco_report(tmp_path):
    executable = _script(tmp_path, "pathlib.Path('args.txt').write_text(' '.join(sys.argv[1:]))")

    MavenClient(executable).jacoco_report(tmp_path)

    assert (tmp_path / "args.txt").read_text() == "-q -B jacoco:report"


@pytest.mark.skipif(os.name == "nt", reason="shell script as mvn")
def test_maven_client_prefers_the_wrapper_and_reports_failures(tmp_path):
    wrapper = Path(_script(tmp_path, "print('[ERROR] plugin non trovato'); sys.exit(1)"))
    wrapper.rename(tmp_path / "mvnw")

    with pytest.raises(UpstreamError, match=r"mvn jacoco:report fallito .*\[ERROR\] plugin non trovato"):
        MavenClient().jacoco_report(tmp_path)


@pytest.mark.skipif(os.name == "nt", reason="shell script as mvn")
def test_maven_client_timeout(tmp_path):
    executable = _script(tmp_path, "import time; time.sleep(5)")

    with pytest.raises(UpstreamError, match="non ha risposto entro 1s"):
        MavenClient(executable, timeout=1).jacoco_report(tmp_path)


def test_maven_client_missing_mvn(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(UpstreamError, match="mvn non trovato"):
        MavenClient().jacoco_report(tmp_path)
    with pytest.raises(UpstreamError, match="Impossibile eseguire mvn"):
        MavenClient(str(tmp_path / "nope")).jacoco_report(tmp_path)


# --------------------------------------------------------------- git: lines

def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def _write(folder: Path, path: str, text: str) -> None:
    file = folder / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(text, encoding="utf-8")


def _commit(folder: Path, message: str = "change") -> None:
    _git(folder, "add", "-A")
    _git(folder, "-c", "user.name=T", "-c", "user.email=t@example.com", "commit", "-q", "-m", message)


def _clone(root: Path, name: str, files: dict[str, str]) -> Path:
    """A repository with ``files`` pushed to its own bare remote."""
    remote = root / ".remotes" / f"{name}.git"
    remote.mkdir(parents=True)
    _git(remote, "init", "-q", "--bare")
    folder = root / name
    _git(root, "clone", "-q", str(remote), name)
    for path, text in files.items():
        _write(folder, path, text)
    _commit(folder, "base")
    _git(folder, "push", "-q", "origin", "HEAD")
    return folder


JAVA = "package net.acme;\n\nclass Orders {\n  int a() { return 1; }\n}\n"


@needs_git
def test_unpushed_range_and_added_lines(tmp_path):
    folder = _clone(tmp_path, "repo", {f"{PKG}/Orders.java": JAVA})
    client = GitClient()
    assert client.unpushed_range(folder) == (0, [])

    _write(folder, f"{PKG}/Orders.java", JAVA.replace("  int a() { return 1; }\n", "  int a() { return 2; }\n  int b() { return 3; }\n"))
    _write(folder, "README.md", "x\n")
    _commit(folder)
    commits, boundaries = client.unpushed_range(folder)

    assert commits == 1 and len(boundaries) == 1
    assert client.added_lines(folder, boundaries[0], "*.java") == {f"{PKG}/Orders.java": {4, 5}}
    assert client.added_lines(folder, None, "*.java") == {f"{PKG}/Orders.java": {1, 2, 3, 4, 5, 6}}  # nothing on a remote: every line
    assert client.commit_timestamp(folder) > 0


@needs_git
def test_unpushed_changes_ignores_what_a_merged_remote_branch_brings(tmp_path, project_store, git_service):
    folder = _clone(tmp_path, "repo", {f"{PKG}/Orders.java": JAVA, f"{PKG}/Other.java": "class Other {}\n"})
    project_store.save(Project(name="P", source=ProjectSource.FOLDER, root_path=str(folder)))
    other = tmp_path / "other"
    _git(tmp_path, "clone", "-q", str(tmp_path / ".remotes" / "repo.git"), "other")
    _write(other, f"{PKG}/Other.java", "class Other {\n  int pushed;\n}\n")
    _commit(other, "pushed by someone else")
    _git(other, "push", "-q", "origin", "HEAD")
    _write(folder, f"{PKG}/Orders.java", JAVA + "// mine\n")
    _commit(folder, "mine")
    _git(folder, "fetch", "-q")
    _git(folder, "-c", "user.name=T", "-c", "user.email=t@example.com", "merge", "-q", "--no-edit", "FETCH_HEAD")

    changes = git_service.unpushed_changes("P", "", "*.java")

    assert changes.commits == 2  # mine + the merge
    assert changes.added_lines == {f"{PKG}/Orders.java": [6]}  # Other.java came from the remote


@needs_git
def test_unpushed_changes_nothing_to_push(tmp_path, project_store, git_service):
    folder = _clone(tmp_path, "repo", {"a.txt": "a\n"})
    project_store.save(Project(name="P", source=ProjectSource.FOLDER, root_path=str(folder)))

    assert git_service.unpushed_changes("P").commits == 0


# ------------------------------------------------------- service and function

def _pom(body: str) -> str:
    return f'<?xml version="1.0"?>\n<project {NS}>\n{body}\n</project>\n'


def _parent(version: str, artifact: str = "acme-parent-lib") -> str:
    return f"<parent><groupId>net.acme</groupId><artifactId>{artifact}</artifactId><version>{version}</version></parent>"


class FakeMaven(MavenClient):
    """Writes the report the test gives for each repository; remembers where it ran."""

    def __init__(self, reports: dict[str, str] | None = None, error: str = ""):
        super().__init__("unused")
        self.calls: list[str] = []
        self._reports = reports or {}
        self._error = error

    def jacoco_report(self, cwd: Path) -> None:
        self.calls.append(cwd.name)
        if self._error:
            raise UpstreamError(self._error)
        for module, text in self._reports.items():
            if (cwd / module / "target" / "jacoco.exec").is_file():
                _write(cwd, f"{module}target/site/jacoco/jacoco.xml", text)


def _exec(folder: Path, module: str = "", age: float = 0) -> None:
    """A jacoco.exec ``age`` seconds in the future of now (positive = newer than the last commit)."""
    file = folder / module / "target" / "jacoco.exec"
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(b"\x01\xc0\xc0")
    stamp = time.time() + age
    os.utime(file, (stamp, stamp))


def _change(folder: Path, path: str, text: str) -> None:
    _write(folder, path, text)
    _commit(folder)


NEW = "package net.acme;\n\nclass Orders {\n  int a() { return 1; }\n  int b() { return 2; }\n  int c() { return 3; }\n}\n"


@pytest.fixture
def shop(tmp_path, project_store):
    """Project "Shop": parent at 2.0.0; ``lib`` and ``svc`` aligned with Java
    not pushed, ``old`` behind, ``tools`` not verifiable, ``front`` without POM."""
    root = tmp_path / "shop"
    root.mkdir()
    _clone(root, "parent-lib", {"pom.xml": _pom("<groupId>net.acme</groupId><artifactId>acme-parent-lib</artifactId><version>2.0.0</version>")})
    lib = _clone(root, "lib", {"pom.xml": _pom("<artifactId>lib</artifactId>" + _parent("2.0.0")), f"{PKG}/Orders.java": JAVA})
    svc = _clone(root, "svc", {
        "pom.xml": _pom("<artifactId>svc</artifactId><version>1</version><properties><acme.libraries.version>2.0.0</acme.libraries.version></properties>"),
        f"core/{PKG}/Orders.java": JAVA,
    })
    old = _clone(root, "old", {"pom.xml": _pom("<artifactId>old</artifactId>" + _parent("1.9.0")), f"{PKG}/Orders.java": JAVA})
    tools = _clone(root, "tools", {"pom.xml": _pom("<artifactId>tools</artifactId>" + _parent("3.3.2", "spring-boot-starter-parent")),
                                   f"{PKG}/Orders.java": JAVA})
    _clone(root, "front", {"package.json": "{}"})
    _change(lib, f"{PKG}/Orders.java", NEW)
    _write(lib, "src/test/java/net/acme/OrdersTest.java", "class OrdersTest {}\n")
    _commit(lib, "test")
    _change(svc, f"core/{PKG}/Orders.java", NEW)
    for folder in (old, tools):
        _change(folder, f"{PKG}/Orders.java", NEW)
        _exec(folder, age=60)
    _exec(lib, age=60)
    _exec(svc, "core/", age=60)
    project_store.save(Project(name="Shop", source=ProjectSource.FOLDER, root_path=str(root)))
    return root


REPORT_LOW = _jacoco({"Orders.java": {4: 1, 5: 1, 6: 0}})
REPORT_HIGH = _jacoco({"Orders.java": {4: 1, 5: 1, 6: 1}})


@needs_git
def test_coverage_only_where_aligned(shop, git_service):
    maven = FakeMaven({"": REPORT_LOW, "core/": REPORT_HIGH})

    result = MavenService(git_service, maven).new_code_coverage("Shop", None, 80, "", "*.libraries.version")

    by_repo = {check.repository: check for check in result.checks}
    assert sorted(maven.calls) == ["lib", "svc"]  # never in old, tools or the parent
    assert (by_repo["lib"].status, by_repo["lib"].covered, by_repo["lib"].total) == (CoverageStatus.BELOW, 1, 2)
    assert [(item.path, item.lines) for item in by_repo["lib"].uncovered] == [(f"{PKG}/Orders.java", [6])]
    assert by_repo["lib"].unpushed == 2 and by_repo["lib"].report_generated and not by_repo["lib"].stale
    assert (by_repo["svc"].status, by_repo["svc"].percent) == (CoverageStatus.ABOVE, 100.0)
    assert (by_repo["old"].status, by_repo["old"].reason) == (CoverageStatus.NOT_ALIGNED, "parent: 1.9.0 → 2.0.0")
    assert by_repo["tools"].status is CoverageStatus.NOT_VERIFIABLE
    assert "né la proprietà *.libraries.version" in by_repo["tools"].reason
    assert by_repo["parent-lib"].status is CoverageStatus.NOTHING_TO_PUSH
    assert result.without_pom == ["front"]


@needs_git
def test_without_property_the_microservices_are_not_verifiable(shop, git_service):
    maven = FakeMaven({"": REPORT_LOW})

    result = MavenService(git_service, maven).new_code_coverage("Shop")

    svc = next(check for check in result.checks if check.repository == "svc")
    assert svc.status is CoverageStatus.NOT_VERIFIABLE and "nessuna proprietà indicata" in svc.reason
    assert maven.calls == ["lib"]


@needs_git
def test_no_parent_found_nothing_runs(shop, git_service):
    maven = FakeMaven()

    result = MavenService(git_service, maven).new_code_coverage("Shop", None, 80, "missing-parent")

    assert maven.calls == []
    assert {check.status for check in result.checks} == {CoverageStatus.NOT_VERIFIABLE}
    assert result.checks[0].reason == "nessun repository del progetto ha artifactId missing-parent"


@needs_git
def test_unresolved_property_is_not_aligned(tmp_path, project_store, git_service):
    root = tmp_path / "p"
    root.mkdir()
    _clone(root, "parent-lib", {"pom.xml": _pom("<artifactId>acme-parent-lib</artifactId><version>2.0.0</version>")})
    _clone(root, "lib", {"pom.xml": _pom("<artifactId>lib</artifactId>" + _parent("2.0.0"))})
    _clone(root, "svc", {"pom.xml": _pom("<artifactId>svc</artifactId><version>1</version>"
                                         "<properties><x.libraries.version>${remote}</x.libraries.version></properties>")})
    project_store.save(Project(name="P", source=ProjectSource.FOLDER, root_path=str(root)))
    maven = FakeMaven()

    result = MavenService(git_service, maven).new_code_coverage("P", "svc", 80, "", "*.libraries.version")

    assert [(c.status, c.reason) for c in result.checks] == [
        (CoverageStatus.NOT_ALIGNED, "x.libraries.version: ${remote} (non risolto) → 2.0.0"),
    ]
    assert maven.calls == []


@needs_git
def test_report_already_there_and_stale(shop, git_service):
    lib = shop / "lib"
    _write(lib, "target/site/jacoco/jacoco.xml", REPORT_HIGH)
    _exec(lib, age=-3600)  # tests ran before the last commit, XML newer than the exec
    maven = FakeMaven()

    check = MavenService(git_service, maven).new_code_coverage("Shop", "lib").checks[0]

    assert maven.calls == [] and not check.report_generated
    assert (check.status, check.stale) == (CoverageStatus.ABOVE, True)


@needs_git
def test_no_report_cases(shop, git_service):
    (shop / "lib" / "target" / "jacoco.exec").unlink()
    service = MavenService(git_service, FakeMaven())
    assert service.new_code_coverage("Shop", "lib").checks[0].reason.startswith("nessun target/jacoco.exec")

    _exec(shop / "lib", age=60)
    failing = MavenService(git_service, FakeMaven(error="mvn jacoco:report fallito: offline"))
    assert failing.new_code_coverage("Shop", "lib").checks[0].reason == "mvn jacoco:report fallito: offline"

    silent = MavenService(git_service, FakeMaven({}))
    assert "non ha scritto" in silent.new_code_coverage("Shop", "lib").checks[0].reason

    other_file = MavenService(git_service, FakeMaven({"": _jacoco({"Else.java": {1: 1}})}))
    check = other_file.new_code_coverage("Shop", "lib").checks[0]
    assert (check.status, check.not_measured) == (CoverageStatus.NO_REPORT, [f"{PKG}/Orders.java"])

    broken = MavenService(git_service, FakeMaven({"": "<rotto"}))
    assert "jacoco.xml non valido" in broken.new_code_coverage("Shop", "lib").checks[0].reason


@needs_git
def test_nothing_to_measure_and_unknown_repository(shop, git_service):
    lib = shop / "lib"
    _git(lib, "push", "-q", "origin", "HEAD")
    _change(lib, "src/test/java/net/acme/MoreTest.java", "class MoreTest {}\n")
    service = MavenService(git_service, FakeMaven())

    check = service.new_code_coverage("Shop", "lib").checks[0]
    assert (check.status, check.reason) == (CoverageStatus.NOTHING_TO_MEASURE, "nessuna riga di src/main/java/ nei commit da pushare")

    _change(lib, f"{PKG}/Orders.java", NEW.replace("class Orders {", "class Orders { // comment"))
    _write(lib, "target/site/jacoco/jacoco.xml", REPORT_HIGH)
    _exec(lib, age=-3600)
    assert service.new_code_coverage("Shop", "lib").checks[0].reason == "nessuna riga eseguibile nei commit da pushare"

    with pytest.raises(ValidationError, match="non è un repository del progetto"):
        service.new_code_coverage("Shop", "nope")
    with pytest.raises(ValidationError, match="tra 1 e 100"):
        service.new_code_coverage("Shop", None, 0)
    assert not service.new_code_coverage("Shop", "front").any_pom


def _run_function(git_service, project_data_service, monkeypatch, maven: FakeMaven, step_input: str = "", **params):
    monkeypatch.setattr("service.maven_service.MavenClient", lambda: maven)
    context = FunctionContext(project_name="Shop", pipeline_input="", git=git_service, project_data=project_data_service)
    return FUNCTION_REGISTRY["coverage_new_code"].execute(context, step_input, params)


@needs_git
def test_function_text_below_threshold_first(shop, git_service, project_data_service, monkeypatch):
    result = _run_function(git_service, project_data_service, monkeypatch, FakeMaven({"": REPORT_LOW, "core/": REPORT_HIGH}),
                           repository="*", property="*.libraries.version")

    sections = result.text.split("\n\n")
    assert sections[0] == "Coverage nuovo codice: 1 repository sotto soglia (80%)."
    assert sections[1] == f"Sotto soglia\n- lib: 50.0% (1/2 righe nuove coperte, 2 commit da pushare)\n  - {PKG}/Orders.java: righe 6"
    assert sections[2] == "Sopra soglia\n- svc: 100.0% (2/2 righe nuove coperte, 1 commit da pushare)"
    assert sections[3] == "Saltati: non allineati al parent acme-parent-lib 2.0.0 (mvn non lanciato)\n- old: parent: 1.9.0 → 2.0.0"
    assert sections[4].startswith("Saltati: allineamento al parent non verificabile (mvn non lanciato)\n- tools: il pom.xml non ha come <parent>")
    assert sections[5] == "Altri: parent-lib (niente da pushare), front (senza pom.xml)."
    assert {check.repository for check in result.coverage.checks} >= {"lib", "svc"}  # declared: masked


@needs_git
def test_function_all_above_and_one_repository_from_the_input(shop, git_service, project_data_service, monkeypatch):
    text = _run_function(git_service, project_data_service, monkeypatch, FakeMaven({"": REPORT_HIGH}), "lib").text

    assert text.startswith("Coverage nuovo codice: tutti sopra soglia (80%).")
    assert coverage_new_code.BELOW_MARK not in text


@needs_git
def test_function_short_texts(tmp_path, project_store, git_service, project_data_service, monkeypatch):
    root = tmp_path / "plain"
    root.mkdir()
    _clone(root, "front", {"package.json": "{}"})
    project_store.save(Project(name="Shop", source=ProjectSource.FOLDER, root_path=str(root)))
    maven = FakeMaven()
    assert _run_function(git_service, project_data_service, monkeypatch, maven, repository="*").text == coverage_new_code.NO_POM
    assert _run_function(git_service, project_data_service, monkeypatch, maven, "front").text == "Coverage: front non ha un pom.xml."

    _clone(root, "parent-lib", {"pom.xml": _pom("<artifactId>acme-parent-lib</artifactId><version>2.0.0</version>")})
    _clone(root, "lib", {"pom.xml": _pom("<artifactId>lib</artifactId>" + _parent("2.0.0"))})
    assert _run_function(git_service, project_data_service, monkeypatch, maven, repository="*").text == coverage_new_code.NOTHING_TO_PUSH


@needs_git
def test_function_nothing_measured_but_skipped(shop, git_service, project_data_service, monkeypatch):
    text = _run_function(git_service, project_data_service, monkeypatch, FakeMaven(), repository="*", parent_artifact_id="missing").text

    assert text.startswith("Coverage nuovo codice (soglia 80%): niente di misurato.")


def test_ranges():
    assert coverage_new_code._ranges([3, 4, 5, 9, 11, 12]) == "3-5, 9, 11-12"
    assert coverage_new_code._ranges([7]) == "7"
