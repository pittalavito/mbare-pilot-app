"""The map of the repositories in context/repository.md, written from
their files and git (no LLM); generating it again keeps the user's notes."""
import shutil
import subprocess
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.container import Container
from domain.project import repository_map
from models.domain.dev import TestKind
from models.domain.project import Project, ProjectSource
from service.repository_map_service import RepositoryMapService

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

POM = """<project xmlns="http://maven.apache.org/POM/4.0.0"><parent><artifactId>{parent}</artifactId></parent>
<artifactId>{name}</artifactId><dependencies>{deps}</dependencies></project>"""


def _repo(root, name, files):
    folder = root / name
    folder.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "develop"], cwd=folder, check=True, capture_output=True)
    for path, text in files.items():
        (folder / path).write_text(text, encoding="utf-8")
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "init"],
                   cwd=folder, check=True, capture_output=True)


@pytest.fixture
def project(tmp_path, project_store):
    root = tmp_path / "shop"
    dep = "<dependency><artifactId>lib-auth</artifactId></dependency><dependency><artifactId>spring-web</artifactId></dependency>"
    _repo(root, "api", {"pom.xml": POM.format(parent="shop-parent", name="api", deps=dep)})
    _repo(root, "lib-auth", {"pom.xml": POM.format(parent="shop-parent", name="lib-auth", deps="")})
    _repo(root, "web", {"package.json": '{"name": "web", "dependencies": {"react": "18"}}'})
    project_store.save(Project(name="shop", source=ProjectSource.FOLDER, root_path=str(root)))
    return root


def test_the_map_says_build_dependencies_order_and_branches_and_keeps_the_notes(project, git_service, project_data_service):
    service = RepositoryMapService(git_service, project_data_service, clock=lambda: datetime(2026, 11, 19, 10, 0))
    assert service.generate("shop") == ("repository.md", None)

    text = project_data_service.read_context("shop", "repository.md")
    assert text.startswith(repository_map.HEADER) and "_Generata il 19/11/2026 10:00._" in text
    assert "## api\n- Build: Maven · build `" in text and "- Nome: lib-auth" in text
    assert "- Usa: lib-auth" in text and "## lib-auth" in text and "- Usato da: api" in text
    assert "## web\n- Build: Node (npm)" in text and "- Branch: corrente develop · principali: develop" in text
    order = text.split("## Ordine di build", 1)[1]
    assert order.index("lib-auth") < order.index("api")

    project_data_service.save_context("shop", "repository.md", "# Repository\n\nNota mia in cima.\n\n" + text.split("\n\n", 2)[2]
                                      + "\nNota mia in fondo.\n")
    service.generate("shop")
    again = project_data_service.read_context("shop", "repository.md")
    assert again.startswith("# Repository\n\nNota mia in cima.") and again.rstrip().endswith("Nota mia in fondo.")
    assert again.count(repository_map.START) == 1


def test_identity_of_the_build_files_and_broken_ones():
    assert repository_map.identity(TestKind.PYTHON, '[project]\nname = "core"\ndependencies = ["requests>=2", "lib-x ; python_version>\'3\'"]') == (
        "core", ["requests", "lib-x"])
    assert repository_map.identity(TestKind.NODE, '{"name": "web", "devDependencies": {"vite": "5"}}') == ("web", ["vite"])
    assert repository_map.identity(TestKind.MAVEN, "<rotto") == ("", [])
    assert repository_map.identity(TestKind.UNKNOWN, "x") == ("", [])
    assert repository_map.main_branches(["develop", "feature/x"], ["origin/main", "origin/HEAD"]) == ["main", "develop"]
    assert repository_map.build_order({"a": ["b"], "b": ["a"], "c": []}) == ["c", "a", "b"]  # a cycle keeps the order
    assert repository_map.merge("", "X").startswith(repository_map.HEADER)
    assert repository_map.merge("# Mio", "X") == "# Mio\n\nX\n"


def test_the_api(project, stores):
    with TestClient(create_app(Container(stores=stores))) as http:
        saved = http.post("/projects/shop/context/repository-map")
        assert saved.status_code == 200 and saved.json()["name"] == "repository.md"
        assert "Ordine di build" in http.get("/projects/shop/context/repository.md").json()["content"]
