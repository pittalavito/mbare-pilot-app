"""GitService on real repositories created in a tmp dir (needs ``git`` on PATH)."""
import shutil
import subprocess

import pytest

from core.error import NotFoundError, UpstreamError, ValidationError
from domain.client.git.client import GitClient, _parse_status
from models.domain.git import GitChangeKind
from models.domain.project import Project, ProjectSource
from service.git_service import GitService

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _repo(folder, *commits):
    """A repository in ``folder`` with one commit per ``(file, message)`` or
    ``(file, message, author name)`` (default author: Ada)."""
    folder.mkdir(parents=True, exist_ok=True)
    _git(folder, "init", "-q")
    _git(folder, "config", "user.name", "Ada")
    _git(folder, "config", "user.email", "ada@example.com")
    for file_name, message, *author in commits:
        path = folder / file_name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(message, encoding="utf-8")
        _git(folder, "add", file_name)
        name = author[0] if author else "Ada"
        _git(folder, "commit", "-q", "-m", message, f"--author={name} <{name.lower()}@example.com>")


@pytest.fixture(scope="module")
def workspace(tmp_path_factory):
    """A project folder holding two repositories and a plain folder (read-only
    for the tests, so built once)."""
    root = tmp_path_factory.mktemp("git") / "workspace"
    _repo(
        root / "api",
        ("main.py", "first api"),
        ("docs/readme.md", "api docs", "Bob"),
        ("main.py", "Fix api (PROJECT-1)", "Bob"),
        ("main.py", "fix api again"),
    )
    _repo(root / "libs" / "core", ("core.py", "core init"))
    (root / "notes").mkdir()
    (root / "node_modules" / "pkg").mkdir(parents=True)
    _repo(root / "node_modules" / "pkg", ("index.js", "vendored"))
    return root


@pytest.fixture
def git_service(workspace, project_store):
    project_store.save(Project(name="Shop", source=ProjectSource.FOLDER, root_path=str(workspace)))
    return GitService(project_store)


def test_repositories_found_in_subfolders(git_service):
    repos = git_service.repositories("Shop")

    assert [(repo.path, repo.name) for repo in repos] == [("api", "api"), ("libs/core", "core")]


def test_project_folder_itself_a_repository(tmp_path, project_store):
    _repo(tmp_path / "single", ("a.txt", "one"))
    project_store.save(Project(name="Single", source=ProjectSource.FOLDER, root_path=str(tmp_path / "single")))

    service = GitService(project_store)

    assert [repo.path for repo in service.repositories("Single")] == [""]
    assert [commit.subject for commit in service.log("Single")] == ["one"]


def test_log_newest_first_with_author_and_date(git_service):
    commits = git_service.log("Shop", "api")

    assert [commit.subject for commit in commits] == ["fix api again", "Fix api (PROJECT-1)", "api docs", "first api"]
    first = commits[0]
    assert (first.author, first.email) == ("Ada", "ada@example.com")
    assert len(first.hash) == 40 and first.hash.startswith(first.short_hash)
    assert first.date.tzinfo is not None


def test_log_limit(git_service):
    assert [commit.subject for commit in git_service.log("Shop", "api", limit=1)] == ["fix api again"]


# ------------------------------------------------------------------ filters

def _subjects(commits):
    return [commit.subject for commit in commits]


def test_filter_by_author_name_or_email_case_insensitive(git_service):
    assert _subjects(git_service.log("Shop", "api", author="bob")) == ["Fix api (PROJECT-1)", "api docs"]
    assert _subjects(git_service.log("Shop", "api", author="ada@EXAMPLE")) == ["fix api again", "first api"]


def test_filter_by_message_is_plain_text(git_service):
    assert _subjects(git_service.log("Shop", "api", message="FIX API")) == ["fix api again", "Fix api (PROJECT-1)"]
    assert _subjects(git_service.log("Shop", "api", message="(PROJECT-1")) == ["Fix api (PROJECT-1)"]


def test_filters_combine(git_service):
    assert _subjects(git_service.log("Shop", "api", author="ada", message="fix")) == ["fix api again"]
    assert git_service.log("Shop", "api", author="nobody") == []


def test_filter_by_commit_hash_also_abbreviated(git_service):
    target = git_service.log("Shop", "api")[2]

    assert git_service.log("Shop", "api", commit=target.hash) == [target]
    assert git_service.log("Shop", "api", commit=target.short_hash[:6]) == [target]
    assert git_service.log("Shop", "api", commit=target.short_hash, author="ada") == []


def test_commit_hash_from_a_subfolder(git_service):
    target = git_service.log("Shop", "api")[0]

    assert git_service.log("Shop", "api/docs", commit=target.short_hash) == [target]


def test_unknown_commit(git_service):
    with pytest.raises(NotFoundError, match="Commit non trovato"):
        git_service.log("Shop", "api", commit="deadbeef")


@pytest.mark.parametrize("commit", ["abc", "HEAD", "--all", "main~1", "g1234"])
def test_invalid_commit_hash_rejected(git_service, commit):
    with pytest.raises(ValidationError, match="Hash"):
        git_service.log("Shop", "api", commit=commit)


def test_log_of_a_subfolder_keeps_only_its_commits(git_service):
    assert [commit.subject for commit in git_service.log("Shop", "api/docs")] == ["api docs"]


@pytest.mark.parametrize("subpath", ["libs/core", "libs\\core", "/libs/core/"])
def test_subpath_separators(git_service, subpath):
    assert [commit.subject for commit in git_service.log("Shop", subpath)] == ["core init"]


def test_folder_outside_any_repository(git_service):
    with pytest.raises(ValidationError, match="repository git"):
        git_service.log("Shop", "notes")


@pytest.mark.parametrize("subpath", ["..", "../..", "api/../../outside"])
def test_subpath_cannot_leave_the_project(git_service, subpath):
    with pytest.raises(ValidationError, match="dentro il progetto"):
        git_service.log("Shop", subpath)


def test_missing_subfolder(git_service):
    with pytest.raises(ValidationError, match="inesistente"):
        git_service.log("Shop", "nope")


@pytest.mark.parametrize("limit", [0, 501])
def test_limit_bounds(git_service, limit):
    with pytest.raises(ValidationError):
        git_service.log("Shop", "api", limit=limit)


def test_unknown_project(git_service):
    with pytest.raises(NotFoundError):
        git_service.log("Nope")


# ------------------------------------------------------------------- status

@pytest.fixture
def dirty(tmp_path, project_store):
    """A fresh repository (project "Dirty") the test can change."""
    root = tmp_path / "dirty"
    _repo(root, ("keep.txt", "keep"), ("edit.txt", "edit"), ("gone.txt", "gone"), ("old.txt", "old"),
          ("src/app.py", "app"))
    project_store.save(Project(name="Dirty", source=ProjectSource.FOLDER, root_path=str(root)))
    return root


def _changes(status):
    return {change.path: (change.kind, change.staged, change.unstaged, change.original_path) for change in status.changes}


def test_status_clean_repository(dirty, project_store):
    status = GitService(project_store).status("Dirty")

    assert status.is_clean
    assert status.branch in {"main", "master"}
    assert (status.upstream, status.ahead, status.behind) == (None, 0, 0)


def test_status_lists_every_kind_of_change(dirty, project_store):
    (dirty / "edit.txt").write_text("changed", encoding="utf-8")
    (dirty / "gone.txt").unlink()
    (dirty / "new file.txt").write_text("untracked", encoding="utf-8")
    (dirty / "added.txt").write_text("added", encoding="utf-8")
    _git(dirty, "add", "added.txt")
    _git(dirty, "mv", "old.txt", "renamed.txt")

    status = GitService(project_store).status("Dirty")

    assert not status.is_clean
    assert _changes(status) == {
        "edit.txt": (GitChangeKind.MODIFIED, False, True, None),
        "gone.txt": (GitChangeKind.DELETED, False, True, None),
        "new file.txt": (GitChangeKind.UNTRACKED, False, True, None),
        "added.txt": (GitChangeKind.ADDED, True, False, None),
        "renamed.txt": (GitChangeKind.RENAMED, True, False, "old.txt"),
    }


def test_status_of_a_subfolder_keeps_only_its_files(dirty, project_store):
    (dirty / "edit.txt").write_text("changed", encoding="utf-8")
    (dirty / "src" / "app.py").write_text("changed", encoding="utf-8")

    status = GitService(project_store).status("Dirty", "src")

    assert list(_changes(status)) == ["src/app.py"]


def test_status_ahead_and_behind_upstream(dirty, tmp_path, project_store):
    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", str(dirty), str(clone))
    _git(clone, "config", "user.name", "Ada")
    _git(clone, "config", "user.email", "ada@example.com")
    (clone / "local.txt").write_text("local", encoding="utf-8")
    _git(clone, "add", "local.txt")
    _git(clone, "commit", "-q", "-m", "local")
    (dirty / "remote.txt").write_text("remote", encoding="utf-8")
    _git(dirty, "add", "remote.txt")
    _git(dirty, "commit", "-q", "-m", "remote")
    _git(clone, "fetch", "-q")
    project_store.save(Project(name="Clone", source=ProjectSource.FOLDER, root_path=str(clone)))

    status = GitService(project_store).status("Clone")

    assert status.upstream and status.upstream.startswith("origin/")
    assert (status.ahead, status.behind) == (1, 1)
    assert status.is_clean


def test_status_outside_a_repository(git_service):
    with pytest.raises(ValidationError, match="repository git"):
        git_service.status("Shop", "notes")


def test_parse_status_conflict_and_detached_head():
    output = "\0".join([
        "# branch.oid 1234abcd",
        "# branch.head (detached)",
        "u UU N... 100644 100644 100644 100644 aaa bbb ccc dir/both changed.txt",
        "",
    ])

    status = _parse_status(output)

    assert status.branch is None
    assert _changes(status) == {"dir/both changed.txt": (GitChangeKind.CONFLICT, False, True, None)}


def test_git_missing_explains_it(workspace, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)

    with pytest.raises(UpstreamError, match="git non trovato"):
        GitClient().log(workspace / "api", 5)
