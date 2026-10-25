"""git_status tool on a real repository (needs ``git`` on PATH):
bound to the run's project, errors returned to the agent as JSON."""
import shutil
import subprocess
from pathlib import Path

import pytest

from fakes import as_dict
from models.domain.project import Project, ProjectSource
from service.git_service import GitService
from tool.context import ToolContext
from tool.list.git.git_status import GIT_STATUS

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def git(store_service, tmp_path):
    """Project "Shop" with a repository ``api`` holding two commits, and an
    "Other" project the tools must never reach."""
    repo = tmp_path / "shop" / "api"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Ada")
    _git(repo, "config", "user.email", "ada@example.com")
    for message in ("first", "second"):
        (repo / "main.py").write_text(message, encoding="utf-8")
        _git(repo, "add", "main.py")
        _git(repo, "commit", "-q", "-m", message)
    (tmp_path / "other").mkdir()
    store_service.save_project(Project(name="Shop", source=ProjectSource.FOLDER, root_path=str(tmp_path / "shop")))
    store_service.save_project(Project(name="Other", source=ProjectSource.FOLDER, root_path=str(tmp_path / "other")))
    return GitService(store_service)


def _call(built, **arguments):
    return as_dict(built.func(**arguments))


def test_git_status_on_the_runs_project(git, tmp_path):
    (tmp_path / "shop" / "api" / "main.py").write_text("changed", encoding="utf-8")

    result = _call(GIT_STATUS.build(ToolContext("Shop", git)), repository="api")

    assert result["clean"] is False
    assert [change["path"] for change in result["status"]["changes"]] == ["main.py"]


def test_the_project_comes_from_the_run_not_from_the_model(git):
    """The same arguments in another project's run find nothing of Shop."""
    result = _call(GIT_STATUS.build(ToolContext("Other", git)), repository="api")

    assert "error" in result and "inesistente" in result["error"]


def test_errors_list_the_available_repositories(git):
    result = _call(GIT_STATUS.build(ToolContext("Shop", git)), repository="nope")

    assert "Cartella inesistente" in result["error"]
    assert "Repository disponibili: api." in result["error"]


def test_escaping_the_project_is_an_error(git):
    result = _call(GIT_STATUS.build(ToolContext("Shop", git)), repository="../other")

    assert "dentro il progetto" in result["error"]


def test_run_without_a_project(git):
    result = _call(GIT_STATUS.build(ToolContext(None, git)), repository="api")

    assert "progetto" in result["error"]
    assert "Repository disponibili" not in result["error"]


def test_tool_schema_requires_every_argument(git):
    built = GIT_STATUS.build(ToolContext("Shop", git))

    assert built.required == ["repository"]
    assert all(not description["description"].startswith("Parameter ") for description in built.properties.values())


def test_errors_hide_the_local_paths(git, tmp_path):
    (tmp_path / "shop" / "plain").mkdir()

    result = _call(GIT_STATUS.build(ToolContext("Shop", git)), repository="plain")

    error = result["error"]
    assert "non è dentro un repository git" in error and "<progetto>" in error
    assert str(tmp_path) not in error and tmp_path.as_posix() not in error and str(Path.home()) not in error


def test_hide_local_paths_any_separator_and_case(git, tmp_path):
    from tool.list.git.errors import hide_local_paths

    folder = str((tmp_path / "shop").resolve())
    text = f"fatal: dubious ownership in '{folder.replace(chr(92), '/').upper()}/api' ({folder}) {Path.home()}\\x"

    assert hide_local_paths(ToolContext("Shop", git), text) == "fatal: dubious ownership in '<progetto>/api' (<progetto>) ~\\x"
