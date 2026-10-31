"""The git tools that change a repository (pull --ff-only, stash), in
GitService and as the agents' tools, on real repositories (needs ``git`` on
PATH): a bare "origin", the project's clone ``shop/api`` and another clone
that pushes new commits."""
import shutil
import subprocess

import pytest

from core.error import NotFoundError, ValidationError
from domain.agent.masking import AgentMask
from fakes import as_dict
from models.domain.project import Project, ProjectSource
from tool.context import ToolContext
from tool.list.git.git_pull_fast_forward import GIT_PULL_FAST_FORWARD

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _identity(repo, name="Ada"):
    _git(repo, "config", "user.name", name)
    _git(repo, "config", "user.email", f"{name.lower()}@example.com")


def _commit(repo, message, file="main.py"):
    (repo / file).write_text(message, encoding="utf-8")
    _git(repo, "add", file)
    _git(repo, "commit", "-q", "-m", message)


@pytest.fixture
def repos(tmp_path, project_store):
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "-q")
    _identity(seed)
    _commit(seed, "first")
    _git(tmp_path, "clone", "-q", "--bare", str(seed), "origin.git")
    (tmp_path / "shop").mkdir()
    _git(tmp_path / "shop", "clone", "-q", str(tmp_path / "origin.git"), "api")
    _identity(tmp_path / "shop" / "api")
    _git(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), "pusher")
    _identity(tmp_path / "pusher", "Bob")
    project_store.save(Project(name="Shop", source=ProjectSource.FOLDER, root_path=str(tmp_path / "shop")))
    return tmp_path


@pytest.fixture
def git(repos, git_service):
    return git_service


def _push(repos, *messages):
    for message in messages:
        _commit(repos / "pusher", message)
    _git(repos / "pusher", "push", "-q")


def test_pull_brings_the_new_commits(git, repos):
    _push(repos, "second", "third")

    result = git.pull_fast_forward("Shop", "api")

    assert [c.subject for c in result.commits] == ["third", "second"] and not result.up_to_date
    assert result.upstream.startswith("origin/")
    assert (repos / "shop" / "api" / "main.py").read_text(encoding="utf-8") == "third"
    assert git.pull_fast_forward("Shop", "api").up_to_date


def test_local_changes_to_tracked_files_refuse_the_pull(git, repos):
    _push(repos, "second")
    (repos / "shop" / "api" / "main.py").write_text("mia modifica", encoding="utf-8")

    with pytest.raises(ValidationError, match="Modifiche locali non committate.*main.py"):
        git.pull_fast_forward("Shop", "api")
    assert (repos / "shop" / "api" / "main.py").read_text(encoding="utf-8") == "mia modifica"


def test_untracked_files_do_not_block(git, repos):
    _push(repos, "second")
    (repos / "shop" / "api" / "appunti.txt").write_text("x", encoding="utf-8")

    assert [c.subject for c in git.pull_fast_forward("Shop", "api").commits] == ["second"]


def test_diverged_branch_is_never_merged(git, repos):
    _push(repos, "remote")
    _commit(repos / "shop" / "api", "local", file="local.py")

    with pytest.raises(ValidationError, match="fast-forward non è possibile"):
        git.pull_fast_forward("Shop", "api")
    log = subprocess.run(["git", "log", "--format=%s"], cwd=repos / "shop" / "api", capture_output=True, text=True).stdout
    assert log.split() == ["local", "first"]  # nothing merged


def test_branch_without_upstream(git, repos):
    _git(repos / "shop" / "api", "checkout", "-q", "-b", "solo-locale")

    with pytest.raises(ValidationError, match="non ha un upstream"):
        git.pull_fast_forward("Shop", "api")


def test_tool_masks_the_authors_that_arrive(git, repos, masking_service):
    _push(repos, "second")
    masking = masking_service
    pull = AgentMask(masking.session("Shop")).wrap([GIT_PULL_FAST_FORWARD.build(ToolContext("Shop", git))])[0]

    result = as_dict(pull.func(repository="api"))

    assert result["updated"] and [c["subject"] for c in result["commits"]] == ["second"]
    assert {(e.category.value, e.value) for e in masking.entries("Shop")} == {
        ("repository", "api"), ("person", "Bob"), ("email", "bob@example.com"),
    }


def test_tool_errors_come_back_to_the_agent(git, repos):
    (repos / "shop" / "api" / "main.py").write_text("mia modifica", encoding="utf-8")

    result = as_dict(GIT_PULL_FAST_FORWARD.build(ToolContext("Shop", git)).func(repository="api"))

    assert "Modifiche locali" in result["error"] and str(repos) not in result["error"]


# -------------------------------------------------------------------- stash

def _stash_list(repo):
    output = subprocess.run(["git", "stash", "list", "--format=%gs"], cwd=repo, capture_output=True, text=True).stdout
    return [line for line in output.splitlines() if line]


def test_stash_puts_aside_tracked_changes_and_keeps_untracked(git, repos):
    api = repos / "shop" / "api"
    (api / "main.py").write_text("mia modifica", encoding="utf-8")
    (api / "appunti.txt").write_text("x", encoding="utf-8")

    result = git.stash("Shop", "api", "prima del pull")

    assert (result.stashed, result.ref, result.files) == (True, "stash@{0}", ["main.py"])
    assert (api / "main.py").read_text(encoding="utf-8") == "first" and (api / "appunti.txt").exists()
    assert "prima del pull" in _stash_list(api)[0]


def test_stash_then_pull(git, repos):
    _push(repos, "second")
    (repos / "shop" / "api" / "main.py").write_text("mia modifica", encoding="utf-8")

    assert git.stash("Shop", "api").message.startswith("mbare-pilot ")
    assert [c.subject for c in git.pull_fast_forward("Shop", "api").commits] == ["second"]


def test_nothing_to_stash(git, repos):
    (repos / "shop" / "api" / "appunti.txt").write_text("solo non tracciato", encoding="utf-8")

    result = git.stash("Shop", "api")

    assert not result.stashed and result.ref is None and _stash_list(repos / "shop" / "api") == []


def test_stash_tool(git, repos, masking_service):
    from tool.list.git.git_stash import GIT_STASH

    (repos / "shop" / "api" / "main.py").write_text("mia modifica", encoding="utf-8")
    masking = masking_service
    stash = AgentMask(masking.session("Shop")).wrap([GIT_STASH.build(ToolContext("Shop", git))])[0]

    result = as_dict(stash.func(repository="api", message=""))

    assert result["stashed"] and result["files"] == ["main.py"]
    assert [e.value for e in masking.entries("Shop")] == ["api"]


# -------------------------------------------------------------- stash apply

def test_apply_brings_the_changes_back_and_keeps_the_stash(git, repos):
    api = repos / "shop" / "api"
    (api / "main.py").write_text("mia modifica", encoding="utf-8")
    git.stash("Shop", "api", "lavoro a metà")

    result = git.stash_apply("Shop", "api")

    assert (result.ref, result.files, result.conflicts) == ("stash@{0}", ["main.py"], [])
    assert "lavoro a metà" in result.message
    assert (api / "main.py").read_text(encoding="utf-8") == "mia modifica"
    assert len(_stash_list(api)) == 1 and _stash_list(api)[0]  # still there


def test_apply_a_given_stash(git, repos):
    api = repos / "shop" / "api"
    for text in ("primo", "secondo"):
        (api / "main.py").write_text(text, encoding="utf-8")
        git.stash("Shop", "api", text)

    assert git.stash_apply("Shop", "api", "1").ref == "stash@{1}"
    assert (api / "main.py").read_text(encoding="utf-8") == "primo"


def test_apply_errors(git, repos):
    with pytest.raises(NotFoundError, match="Nessuno stash"):
        git.stash_apply("Shop", "api")
    (repos / "shop" / "api" / "main.py").write_text("x", encoding="utf-8")
    git.stash("Shop", "api")
    with pytest.raises(NotFoundError, match="Stash disponibili: stash@\\{0\\}"):
        git.stash_apply("Shop", "api", "stash@{5}")
    with pytest.raises(ValidationError, match="Stash non valido"):
        git.stash_apply("Shop", "api", "ultimo")
    (repos / "shop" / "api" / "main.py").write_text("altra modifica", encoding="utf-8")
    with pytest.raises(ValidationError, match="Modifiche locali"):
        git.stash_apply("Shop", "api")


def test_apply_reports_conflicts(git, repos):
    api = repos / "shop" / "api"
    (api / "main.py").write_text("dallo stash", encoding="utf-8")
    git.stash("Shop", "api")
    _commit(api, "nel frattempo")  # main.py changed and committed after the stash

    result = git.stash_apply("Shop", "api")

    assert result.conflicts == ["main.py"] and result.files == []
    assert len(_stash_list(api)) == 1  # the stash is kept


def test_stash_apply_tool(git, repos):
    from tool.list.git.git_stash_apply import GIT_STASH_APPLY

    (repos / "shop" / "api" / "main.py").write_text("mia modifica", encoding="utf-8")
    git.stash("Shop", "api")

    result = as_dict(GIT_STASH_APPLY.build(ToolContext("Shop", git)).func(repository="api", stash=""))

    assert (result["applied"], result["ref"], result["files"]) == (True, "stash@{0}", ["main.py"])
