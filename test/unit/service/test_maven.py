"""Reading a pom.xml (domain/maven/pom.py) and comparing the root POMs of a
project with its parent POM (MavenService, function maven_parent_alignment),
on real repositories in a tmp dir (needs ``git`` on PATH)."""
import shutil
import subprocess

import pytest

from core.error import ValidationError
from domain.maven.pom import parse_pom
from function.context import FunctionContext
from function.registry import FUNCTION_REGISTRY
from models.domain.maven import PomCheckKind
from models.domain.project import Project, ProjectSource
from service.maven_service import MavenService

NS = 'xmlns="http://maven.apache.org/POM/4.0.0"'


def _pom(body: str, namespace: bool = True) -> str:
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<project {NS if namespace else ""}>\n{body}\n</project>\n'


def _parent(version: str, artifact: str = "acme-parent-lib") -> str:
    return f"<parent><groupId>net.acme</groupId><artifactId>{artifact}</artifactId><version>{version}</version></parent>"


# ------------------------------------------------------------------ parsing

@pytest.mark.parametrize("namespace", [True, False])
def test_parse_reads_ids_version_parent_and_properties(namespace):
    pom = parse_pom(_pom(
        "<groupId>net.acme</groupId><artifactId>orders</artifactId><version>1.2.0</version>"
        + _parent("2.678.0")
        + "<properties><acme.libraries.version>2.678.0</acme.libraries.version><java.version>21</java.version></properties>",
        namespace,
    ))

    assert (pom.group_id, pom.artifact_id, pom.version) == ("net.acme", "orders", "1.2.0")
    assert pom.parent and (pom.parent.artifact_id, pom.parent.version) == ("acme-parent-lib", "2.678.0")
    assert pom.properties == {"acme.libraries.version": "2.678.0", "java.version": "21"}


def test_group_and_version_inherited_from_the_parent():
    pom = parse_pom(_pom("<artifactId>core-lib</artifactId>" + _parent("2.678.0")))

    assert (pom.group_id, pom.version) == ("net.acme", "2.678.0")


def test_placeholders_resolved_from_the_pom_itself():
    pom = parse_pom(_pom(
        "<artifactId>orders</artifactId><version>1.0.0</version>" + _parent("2.678.0")
        + "<properties><libs>${base}</libs><base>2.${minor}.0</base><minor>679</minor>"
        "<same>${project.version}</same><up>${project.parent.version}</up><remote>${from.nexus}</remote></properties>"
    ))

    assert pom.properties["libs"] == "2.679.0"  # a property pointing to another, two levels
    assert (pom.properties["same"], pom.properties["up"]) == ("1.0.0", "2.678.0")
    assert pom.properties["remote"] == "${from.nexus}"  # not in the POM: left as it is


def test_parent_version_from_a_property():
    pom = parse_pom(_pom("<artifactId>x</artifactId>" + _parent("${revision}") + "<properties><revision>3.0.1</revision></properties>"))

    assert pom.parent and pom.parent.version == "3.0.1"


def test_comments_are_ignored_and_bytes_keep_the_declared_encoding():
    text = _pom("<!-- già -->\n<artifactId>città</artifactId><version>1</version>")

    assert parse_pom(text.encode("utf-8")).artifact_id == "città"


@pytest.mark.parametrize("text, message", [
    ("non è xml", "pom.xml non valido"),
    ("<settings/>", "non <project>"),
])
def test_invalid_pom(text, message):
    with pytest.raises(ValidationError, match=message):
        parse_pom(text)


# ---------------------------------------------------------------- alignment

pytestmark_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _repo(root, name, pom: str | None):
    folder = root / name
    folder.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=folder, check=True, capture_output=True)
    if pom is not None:
        (folder / "pom.xml").write_text(pom, encoding="utf-8")


@pytest.fixture
def maven(tmp_path, project_store, git_service):
    """Project "Shop": the parent at 2.679.0, two libraries, two
    microservices, a repository without POM, one not Java-related and one broken."""
    root = tmp_path / "shop"
    _repo(root, "parent-lib", _pom("<groupId>net.acme</groupId><artifactId>acme-parent-lib</artifactId><version>2.679.0</version>"))
    _repo(root, "core-lib", _pom("<artifactId>core-lib</artifactId>" + _parent("2.679.0")))
    _repo(root, "old-lib", _pom("<artifactId>old-lib</artifactId>" + _parent("2.678.0")))
    _repo(root, "orders", _pom(
        "<artifactId>orders</artifactId><version>1.0.0</version><properties><acme.libraries.version>2.678.0</acme.libraries.version></properties>"
    ))
    _repo(root, "billing", _pom(
        "<artifactId>billing</artifactId><version>1.0.0</version><properties><acme.libraries.version>2.679.0</acme.libraries.version></properties>"
    ))
    _repo(root, "frontend", None)
    _repo(root, "tools", _pom("<artifactId>tools</artifactId><version>9</version>" + _parent("3.3.2", "spring-boot-starter-parent")))
    _repo(root, "rotto", "<project><artifactId>")
    project_store.save(Project(name="Shop", source=ProjectSource.FOLDER, root_path=str(root)))
    return MavenService(git_service)


@pytestmark_git
def test_alignment_with_the_parent(maven):
    result = maven.parent_alignment("Shop", "acme-parent-lib", "acme.libraries.version")

    assert (result.reference_repository, result.reference_version) == ("parent-lib", "2.679.0")
    assert [(c.repository, c.kind, c.value, c.aligned) for c in result.checks] == [
        ("billing", PomCheckKind.PROPERTY, "2.679.0", True),
        ("core-lib", PomCheckKind.PARENT, "2.679.0", True),
        ("old-lib", PomCheckKind.PARENT, "2.678.0", False),
        ("orders", PomCheckKind.PROPERTY, "2.678.0", False),
    ]
    assert [item.repository for item in result.unreadable] == ["rotto"]
    assert (result.without_pom, result.not_relevant) == (["frontend"], ["tools"])


@pytestmark_git
def test_without_property_only_the_libraries(maven):
    result = maven.parent_alignment("Shop", "acme-parent-lib")

    assert {c.repository for c in result.checks} == {"core-lib", "old-lib"}
    assert "orders" in result.not_relevant


@pytestmark_git
def test_unknown_parent_has_no_reference(maven):
    result = maven.parent_alignment("Shop", "nope-parent")

    assert result.reference_repository is None and result.checks == []


@pytestmark_git
def test_empty_parent_is_recognised(maven):
    result = maven.parent_alignment("Shop", "", "acme.libraries.version")

    assert (result.parent_artifact_id, result.detected) == ("acme-parent-lib", True)
    assert (result.reference_repository, result.reference_version) == ("parent-lib", "2.679.0")
    assert {(c.repository, c.aligned) for c in result.checks} == {
        ("billing", True), ("core-lib", True), ("old-lib", False), ("orders", False),
    }


@pytestmark_git
def test_the_parent_named_by_the_most_repositories_wins(tmp_path, project_store, git_service):
    root = tmp_path / "two-parents"
    _repo(root, "a-parent", _pom("<artifactId>a-parent</artifactId><version>1</version>"))
    _repo(root, "b-parent", _pom("<artifactId>b-parent</artifactId><version>2</version>"))
    _repo(root, "lib1", _pom("<artifactId>lib1</artifactId>" + _parent("2", "b-parent")))
    _repo(root, "lib2", _pom("<artifactId>lib2</artifactId>" + _parent("2", "b-parent")))
    _repo(root, "lib3", _pom("<artifactId>lib3</artifactId>" + _parent("1", "a-parent")))
    _repo(root, "boot", _pom("<artifactId>boot</artifactId>" + _parent("3.3.2", "spring-boot-starter-parent")))  # not in the project
    project_store.save(Project(name="Two", source=ProjectSource.FOLDER, root_path=str(root)))

    assert MavenService(git_service).parent_alignment("Two").parent_artifact_id == "b-parent"


@pytestmark_git
def test_no_repository_is_a_parent(tmp_path, project_store, git_service):
    root = tmp_path / "flat"
    _repo(root, "boot", _pom("<artifactId>boot</artifactId>" + _parent("3.3.2", "spring-boot-starter-parent")))
    project_store.save(Project(name="Flat", source=ProjectSource.FOLDER, root_path=str(root)))

    result = MavenService(git_service).parent_alignment("Flat")

    assert (result.parent_artifact_id, result.reference_repository, result.checks) == ("", None, [])
    assert result.not_relevant == ["boot"]


@pytestmark_git
def test_property_pattern(tmp_path, project_store, git_service):
    root = tmp_path / "pattern"
    _repo(root, "parent-lib", _pom("<artifactId>p</artifactId><version>2.0</version>"))
    _repo(root, "svc", _pom(
        "<artifactId>svc</artifactId><version>1</version>"
        "<properties><one.libraries.version>2.0</one.libraries.version><two.libraries.version>1.9</two.libraries.version>"
        "<java.version>21</java.version></properties>"
    ))
    _repo(root, "lib", _pom("<artifactId>lib</artifactId>" + _parent("2.0", "p")))
    project_store.save(Project(name="Pattern", source=ProjectSource.FOLDER, root_path=str(root)))

    result = MavenService(git_service).parent_alignment("Pattern", "", "*.libraries.version")

    assert [(c.repository, c.name, c.value, c.aligned) for c in result.checks] == [
        ("lib", "parent", "2.0", True),
        ("svc", "one.libraries.version", "2.0", True),
        ("svc", "two.libraries.version", "1.9", False),
    ]


def _function(git_service, project_data_service, **params):
    context = FunctionContext(project_name="Shop", pipeline_input="", git=git_service, project_data=project_data_service)
    return FUNCTION_REGISTRY["maven_parent_alignment"].execute(context, "", params)


@pytestmark_git
def test_function_report_puts_the_ones_to_align_first(maven, git_service, project_data_service):
    result = _function(git_service, project_data_service, parent_artifact_id="acme-parent-lib", property="acme.libraries.version")

    sections = result.text.split("\n\n")
    assert sections[0] == "POM: allineamento al parent acme-parent-lib 2.679.0 (parent-lib): 2 da allineare, 2 allineati."
    assert sections[1] == "Da allineare\n- old-lib · parent: 2.678.0 → 2.679.0\n- orders · acme.libraries.version: 2.678.0 → 2.679.0"
    assert sections[2] == "Allineati\n- billing · acme.libraries.version: 2.679.0\n- core-lib · parent: 2.679.0"
    assert sections[3].startswith("Non letti\n- rotto: pom.xml non valido")
    assert sections[4] == "Senza questi campi: tools, frontend (senza pom.xml)."
    assert [c.repository for c in result.alignment.checks]  # declared: the repositories get masked


@pytestmark_git
def test_function_all_aligned_and_unresolved(tmp_path, project_store, git_service, project_data_service):
    root = tmp_path / "small"
    _repo(root, "parent-lib", _pom("<artifactId>acme-parent-lib</artifactId><version>2.0.0</version>"))
    _repo(root, "lib", _pom("<artifactId>lib</artifactId>" + _parent("2.0.0")))
    project_store.save(Project(name="Shop", source=ProjectSource.FOLDER, root_path=str(root)))

    text = _function(git_service, project_data_service, parent_artifact_id="acme-parent-lib").text
    assert text == "POM: allineamento al parent acme-parent-lib 2.0.0 (parent-lib): tutti allineati (1).\n\nAllineati\n- lib · parent: 2.0.0"

    (root / "lib" / "pom.xml").write_text(_pom("<artifactId>lib</artifactId>" + _parent("${from.nexus}")), encoding="utf-8")
    text = _function(git_service, project_data_service, parent_artifact_id="acme-parent-lib").text
    assert "- lib · parent (non risolto): ${from.nexus} → 2.0.0" in text


@pytestmark_git
def test_function_recognised_parent_and_pattern(maven, git_service, project_data_service):
    text = _function(git_service, project_data_service, property="*.libraries.version").text

    assert text.startswith("POM: allineamento al parent acme-parent-lib 2.679.0 (parent-lib, riconosciuto): 2 da allineare, 2 allineati.")
    assert "- orders · acme.libraries.version: 2.678.0 → 2.679.0" in text


@pytestmark_git
def test_function_in_a_project_without_poms(tmp_path, project_store, git_service, project_data_service):
    root = tmp_path / "web-only"
    _repo(root, "frontend", None)
    _repo(root, "site", None)
    project_store.save(Project(name="Shop", source=ProjectSource.FOLDER, root_path=str(root)))

    assert _function(git_service, project_data_service).text == "POM: nessun pom.xml nei repository del progetto."


@pytestmark_git
def test_function_without_a_parent_recognised(tmp_path, project_store, git_service, project_data_service):
    root = tmp_path / "flat"
    _repo(root, "svc", _pom("<artifactId>svc</artifactId><version>1</version><properties><x.libraries.version>1</x.libraries.version></properties>"))
    project_store.save(Project(name="Shop", source=ProjectSource.FOLDER, root_path=str(root)))

    text = _function(git_service, project_data_service, property="*.libraries.version").text

    assert text.startswith("POM: nessun parent riconosciuto")
    assert "- svc · x.libraries.version: 1 → ?" in text


@pytestmark_git
def test_function_without_a_reference_still_lists_the_values(maven, git_service, project_data_service):
    text = _function(git_service, project_data_service, parent_artifact_id="nope", property="acme.libraries.version").text

    assert text.startswith("POM: nessun repository del progetto ha artifactId nope, niente versione di riferimento.")
    assert "- orders · acme.libraries.version: 2.678.0 → ?" in text


# --------------------------------------------- parent in a module, diagnostics

def _write(folder, pom):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "pom.xml").write_text(pom, encoding="utf-8")


@pytest.fixture
def multi_module(tmp_path, project_store, git_service):
    """The parent POM is a module of the "parent" repository, whose root is an
    aggregator with another artifactId."""
    root = tmp_path / "multi"
    _repo(root, "parent", _pom("<artifactId>acme-parent</artifactId><version>1</version><packaging>pom</packaging>"))
    _write(root / "parent" / "parent-lib", _pom("<artifactId>acme-parent-lib</artifactId><version>2.679.0</version>"))
    # copies under target/ and src/ are never the parent
    _write(root / "parent" / "target" / "x", _pom("<artifactId>acme-parent-lib</artifactId><version>0.0.1</version>"))
    _repo(root, "core-lib", _pom("<artifactId>core-lib</artifactId>" + _parent("2.678.0")))
    _repo(root, "orders", _pom("<artifactId>orders</artifactId><version>1</version>"
                               "<properties><acme.libraries.version>2.679.0</acme.libraries.version></properties>"))
    project_store.save(Project(name="Multi", source=ProjectSource.FOLDER, root_path=str(root)))
    return MavenService(git_service)


@pytestmark_git
def test_parent_kept_in_a_module_is_recognised(multi_module):
    result = multi_module.parent_alignment("Multi", "", "*.libraries.version")

    assert (result.parent_artifact_id, result.reference_repository, result.reference_pom, result.reference_version) == (
        "acme-parent-lib", "parent", "parent-lib/pom.xml", "2.679.0")
    assert [(c.repository, c.value, c.aligned) for c in result.checks] == [("core-lib", "2.678.0", False), ("orders", "2.679.0", True)]
    assert result.not_relevant == []  # the aggregator holding the parent is not listed


@pytestmark_git
def test_parent_kept_in_a_module_given_by_name(multi_module):
    assert multi_module.parent_alignment("Multi", "acme-parent-lib").reference_pom == "parent-lib/pom.xml"


@pytestmark_git
def test_report_names_the_module_of_the_parent(multi_module, git_service, project_data_service):
    context = FunctionContext(project_name="Multi", pipeline_input="", git=git_service, project_data=project_data_service)

    text = FUNCTION_REGISTRY["maven_parent_alignment"].execute(context, "", {"property": "*.libraries.version"}).text

    assert text.startswith("POM: allineamento al parent acme-parent-lib 2.679.0 (parent/parent-lib/pom.xml, riconosciuto): 1 da allineare")


@pytestmark_git
def test_report_says_which_parents_and_properties_it_saw(tmp_path, project_store, git_service, project_data_service):
    root = tmp_path / "unknown"
    _repo(root, "a", _pom("<artifactId>a</artifactId>" + _parent("2.678.0") + "<properties><java.version>21</java.version></properties>"))
    _repo(root, "b", _pom("<artifactId>b</artifactId>" + _parent("2.678.0")
                          + "<properties><acme-libs.version>2.678.0</acme-libs.version></properties>"))
    _repo(root, "c", _pom("<artifactId>c</artifactId>" + _parent("3.3.2", "spring-boot-starter-parent")))
    project_store.save(Project(name="Unknown", source=ProjectSource.FOLDER, root_path=str(root)))
    context = FunctionContext(project_name="Unknown", pipeline_input="", git=git_service, project_data=project_data_service)

    text = FUNCTION_REGISTRY["maven_parent_alignment"].execute(context, "", {"property": "*.libraries.version"}).text

    assert text.startswith("POM: nessun parent riconosciuto")
    assert ("Parent dichiarati dai pom.xml del progetto: acme-parent-lib (2), spring-boot-starter-parent (1). "
            "Nessuno è un pom.xml dei repository del progetto (cercato alla radice e nei moduli).") in text
    assert "Nessuna proprietà corrisponde a *.libraries.version. Proprietà con «version» nei pom.xml: acme-libs.version, java.version." in text
