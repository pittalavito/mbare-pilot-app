"""The everyday git commands (log, diff, fetch, branches, checkout, create
branch, commit, push, stash list, pull of every repository on a branch) in
GitService, as the agents' tools and as pipeline functions, on real
repositories (needs ``git`` on PATH): a bare "origin", the project "Shop"
with two clones ``api`` and ``web``, and another clone that pushes."""
import shutil
import subprocess

import pytest

from core.error import NotFoundError, UpstreamError, ValidationError
from domain.agent.masking import AgentMask
from domain.client.git.client import _parse_numstat
from fakes import as_dict
from function.context import FunctionContext
from function.registry import FUNCTION_REGISTRY
from models.domain.git import GitBulkStatus
from models.domain.project import Project, ProjectSource
from tool.context import ToolContext
from tool.registry import TOOL_REGISTRY

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _git(cwd, *args) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


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
    _git(seed, "init", "-q", "-b", "main")
    _identity(seed)
    _commit(seed, "first")
    _git(seed, "branch", "develop")
    _git(tmp_path, "clone", "-q", "--bare", str(seed), "origin.git")
    (tmp_path / "shop").mkdir()
    for name in ("api", "web"):
        _git(tmp_path / "shop", "clone", "-q", str(tmp_path / "origin.git"), name)
        _identity(tmp_path / "shop" / name)
    _git(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), "pusher")
    _identity(tmp_path / "pusher", "Bob")
    project_store.save(Project(name="Shop", source=ProjectSource.FOLDER, root_path=str(tmp_path / "shop")))
    return tmp_path


@pytest.fixture
def git(git_service, repos):
    return git_service


@pytest.fixture
def api(repos):
    return repos / "shop" / "api"


def _push(repos, *messages, branch="main"):
    pusher = repos / "pusher"
    _git(pusher, "checkout", "-q", branch)
    for message in messages:
        _commit(pusher, message)
    _git(pusher, "push", "-q", "origin", branch)


def _tool(name, git, project="Shop"):
    return TOOL_REGISTRY[name].build(ToolContext(project, git))


# ---------------------------------------------------------------- fetch

def test_fetch_tells_what_arrived_without_pulling(git, repos, api):
    _push(repos, "second", "third")

    result = git.fetch("Shop", "api")

    assert (result.branch, result.upstream, result.ahead, result.behind) == ("main", "origin/main", 0, 2)
    assert (api / "main.py").read_text(encoding="utf-8") == "first"


def test_fetch_prunes_deleted_remote_branches(git, repos):
    _git(repos / "pusher", "push", "-q", "origin", "main:old-feature")
    git.fetch("Shop", "api")
    assert "origin/old-feature" in git.branches("Shop", "api").remote
    _git(repos / "pusher", "push", "-q", "origin", "--delete", "old-feature")

    git.fetch("Shop", "api")

    assert "origin/old-feature" not in git.branches("Shop", "api").remote


# ------------------------------------------------------------- branches

def test_branches_local_and_remote(git, repos, api):
    _commit(api, "local", file="local.py")

    result = git.branches("Shop", "api")

    assert result.current == "main"
    [main] = result.local
    assert (main.name, main.current, main.upstream, main.ahead, main.behind) == ("main", True, "origin/main", 1, 0)
    assert main.last_subject == "local" and main.last_commit_date is not None
    assert result.remote == ["origin/develop", "origin/main"]


# ------------------------------------------------------------- checkout

def test_checkout_a_remote_branch_creates_a_tracking_one(git, api):
    result = git.checkout("Shop", "api", "develop")

    assert (result.previous, result.branch, result.created, result.upstream) == ("main", "develop", True, "origin/develop")
    assert git.checkout("Shop", "api", "main").created is False
    assert git.checkout("Shop", "api", "main").previous == "main"  # already there: nothing to do


def test_checkout_refused_with_local_changes(git, api):
    (api / "main.py").write_text("mia modifica", encoding="utf-8")

    with pytest.raises(ValidationError, match="Modifiche locali.*main.py"):
        git.checkout("Shop", "api", "develop")
    assert git.status("Shop", "api").branch == "main"


def test_checkout_unknown_or_invalid_branch(git):
    with pytest.raises(NotFoundError, match="Branch non trovato"):
        git.checkout("Shop", "api", "nope")
    for name in ("", "-f", "a..b", "@{-1}"):
        with pytest.raises(ValidationError):
            git.checkout("Shop", "api", name)


# -------------------------------------------------------- create branch

def test_create_branch_from_here_keeps_the_changes(git, api):
    (api / "main.py").write_text("lavoro in corso", encoding="utf-8")

    result = git.create_branch("Shop", "api", "feature/login")

    assert (result.previous, result.branch, result.created, result.upstream) == ("main", "feature/login", True, None)
    assert (api / "main.py").read_text(encoding="utf-8") == "lavoro in corso"


def test_create_branch_from_a_start_point(git, repos, api):
    _push(repos, "on develop", branch="develop")
    git.fetch("Shop", "api")

    result = git.create_branch("Shop", "api", "hotfix", "origin/develop")

    assert result.upstream == "origin/develop"
    assert (api / "main.py").read_text(encoding="utf-8") == "on develop"


def test_create_branch_errors(git):
    with pytest.raises(ValidationError, match="esiste già"):
        git.create_branch("Shop", "api", "main")
    with pytest.raises(NotFoundError, match="Punto di partenza"):
        git.create_branch("Shop", "api", "x", "origin/nope")


# ------------------------------------------------------------------ diff

def test_diff_unstaged_staged_and_untracked(git, api):
    (api / "main.py").write_text("changed\n", encoding="utf-8")
    (api / "staged.txt").write_text("staged\n", encoding="utf-8")
    _git(api, "add", "staged.txt")
    (api / "nuovo.txt").write_text("x", encoding="utf-8")

    unstaged = git.diff("Shop", "api")
    staged = git.diff("Shop", "api", staged=True)

    assert [(f.path, f.added, f.deleted) for f in unstaged.files] == [("main.py", 1, 1)]
    assert "+changed" in unstaged.patch and unstaged.untracked == ["nuovo.txt"]
    assert [f.path for f in staged.files] == ["staged.txt"] and staged.untracked == []


def test_diff_of_a_commit_and_truncation(git, api):
    _commit(api, "second\n" * 50)
    commit = git.log("Shop", "api", 1)[0]

    result = git.diff("Shop", "api", commit=commit.short_hash, max_chars=100)

    assert [f.path for f in result.files] == ["main.py"]
    assert result.truncated and len(result.patch) == 100
    with pytest.raises(ValidationError, match="Hash"):
        git.diff("Shop", "api", commit="HEAD~1")


def test_clean_diff_is_empty(git):
    result = git.diff("Shop", "api")

    assert (result.files, result.patch, result.truncated) == ([], "", False)


def test_parse_numstat_rename_and_binary():
    output = "1\t2\ta.py\0-\t-\timg.png\0" + "0\t0\t\0old.py\0new.py\0"

    assert [(f.path, f.added, f.deleted, f.binary) for f in _parse_numstat(output)] == [
        ("a.py", 1, 2, False), ("img.png", 0, 0, True), ("new.py", 0, 0, False),
    ]


# ---------------------------------------------------------------- commit

def test_commit_everything(git, api):
    (api / "main.py").write_text("changed", encoding="utf-8")
    (api / "nuovo.txt").write_text("x", encoding="utf-8")

    result = git.commit("Shop", "api", "Aggiorna main")

    assert result.branch == "main" and result.commit.subject == "Aggiorna main"
    assert sorted(result.files) == ["main.py", "nuovo.txt"]
    assert git.status("Shop", "api").is_clean


def test_commit_only_the_given_files(git, api):
    (api / "main.py").write_text("changed", encoding="utf-8")
    (api / "altro.txt").write_text("x", encoding="utf-8")

    result = git.commit("Shop", "api", "Solo main", ["main.py"])

    assert result.files == ["main.py"]
    assert [c.path for c in git.status("Shop", "api").changes] == ["altro.txt"]


def test_commit_errors(git, api):
    with pytest.raises(ValidationError, match="obbligatorio"):
        git.commit("Shop", "api", "  ")
    with pytest.raises(ValidationError, match="Niente da committare"):
        git.commit("Shop", "api", "vuoto")
    with pytest.raises(ValidationError, match="dentro il repository"):
        git.commit("Shop", "api", "fuori", ["../web/main.py"])
    _git(api, "checkout", "-q", "--detach")
    (api / "main.py").write_text("changed", encoding="utf-8")
    with pytest.raises(ValidationError, match="HEAD staccato"):
        git.commit("Shop", "api", "staccato")


# ------------------------------------------------------------------ push

def test_push_sends_the_new_commits(git, repos, api):
    _commit(api, "uno")
    _commit(api, "due")

    result = git.push("Shop", "api")

    assert (result.branch, result.upstream, result.upstream_created) == ("main", "origin/main", False)
    assert [c.subject for c in result.commits] == ["due", "uno"]
    assert _git(repos / "origin.git", "log", "--format=%s", "main").split() == ["due", "uno", "first"]
    assert git.push("Shop", "api").commits == []  # nothing left


def test_push_a_new_branch_sets_its_upstream(git, repos, api):
    git.create_branch("Shop", "api", "feature/x")
    _commit(api, "feature work")

    result = git.push("Shop", "api")

    assert (result.upstream, result.upstream_created) == ("origin/feature/x", True)
    assert [c.subject for c in result.commits] == ["feature work"]
    assert git.status("Shop", "api").upstream == "origin/feature/x"
    assert _git(repos / "origin.git", "log", "--format=%s", "feature/x").split()[0] == "feature"


def test_push_refused_when_behind(git, repos, api):
    _push(repos, "remote")
    _commit(api, "local", file="local.py")

    git.fetch("Shop", "api")
    with pytest.raises(ValidationError, match="fai prima il pull"):
        git.push("Shop", "api")


def test_push_rejected_by_the_remote_without_a_fetch(git, repos, api):
    _push(repos, "remote")
    _commit(api, "local", file="local.py")

    with pytest.raises(ValidationError, match="Push rifiutato"):
        git.push("Shop", "api")
    assert _git(repos / "origin.git", "log", "--format=%s", "main").split() == ["remote", "first"]


# ------------------------------------------------------------ stash list

def test_stash_list(git, api):
    assert git.stash_list("Shop", "api") == []
    (api / "main.py").write_text("x", encoding="utf-8")
    git.stash("Shop", "api", "prima")

    [stash] = git.stash_list("Shop", "api")

    assert stash.ref == "stash@{0}" and "prima" in stash.message


# ------------------------------------------------------ pull all by branch

def _local_develop(git, *names):
    """A local ``develop`` in each repository, left behind on main."""
    for name in names:
        git.checkout("Shop", name, "develop")
        git.checkout("Shop", name, "main")


def test_pull_all_by_branch(git, repos):
    _local_develop(git, "api")
    _push(repos, "on develop", branch="develop")
    web = repos / "shop" / "web"
    (web / "main.py").write_text("lavoro in corso", encoding="utf-8")

    outcomes = {o.repository: o for o in git.pull_all_by_branch("Shop", "develop")}

    assert outcomes["api"].status is GitBulkStatus.UPDATED and outcomes["api"].switched
    assert (outcomes["api"].previous, [c.subject for c in outcomes["api"].commits]) == ("main", ["on develop"])
    assert outcomes["web"].status is GitBulkStatus.SKIPPED and "main.py" in outcomes["web"].reason
    assert git.status("Shop", "web").branch == "main"
    assert git.pull_all_by_branch("Shop", "develop")[0].status is GitBulkStatus.UP_TO_DATE


def test_pull_all_creates_the_branch_from_the_remote(git, repos):
    _push(repos, "on develop", branch="develop")

    outcome = git.pull_all_by_branch("Shop", "develop")[0]

    assert (outcome.status, outcome.switched) == (GitBulkStatus.UP_TO_DATE, True)
    assert (repos / "shop" / "api" / "main.py").read_text(encoding="utf-8") == "on develop"


def test_pull_all_skips_repositories_without_the_branch(git):
    outcomes = git.pull_all_by_branch("Shop", "release")

    assert {o.status for o in outcomes} == {GitBulkStatus.SKIPPED}
    assert all("non c'è" in o.reason for o in outcomes)


def test_pull_all_reports_a_broken_remote_and_goes_on(git, repos):
    _git(repos / "shop" / "web", "remote", "set-url", "origin", str(repos / "missing.git"))

    outcomes = {o.repository: o for o in git.pull_all_by_branch("Shop", "main")}

    assert outcomes["web"].status is GitBulkStatus.FAILED
    assert outcomes["api"].status is GitBulkStatus.UP_TO_DATE


# ----------------------------------------------------------------- tools

def test_every_new_tool_answers(git, repos, api):
    (api / "main.py").write_text("changed", encoding="utf-8")

    assert as_dict(_tool("git_diff", git).func(repository="api", staged=False, commit=""))["files"][0]["path"] == "main.py"
    assert as_dict(_tool("git_log", git).func(repository="api", limit=5, author="", message="", commit=""))["commits"][0]["subject"] == "first"
    assert as_dict(_tool("git_branches", git).func(repository="api"))["current"] == "main"
    assert as_dict(_tool("git_fetch", git).func(repository="api"))["behind"] == 0
    assert as_dict(_tool("git_stash_list", git).func(repository="api"))["stashes"] == []
    created = as_dict(_tool("git_create_branch", git).func(repository="api", name="feature/y", start_point=""))
    assert created["branch"] == "feature/y" and created["created"]
    committed = as_dict(_tool("git_commit", git).func(repository="api", message="Tool commit", files=[]))
    assert committed["files"] == ["main.py"] and committed["commit"]["subject"] == "Tool commit"
    pushed = as_dict(_tool("git_push", git).func(repository="api"))
    assert pushed["pushed"] and pushed["upstream_created"]
    assert as_dict(_tool("git_checkout", git).func(repository="api", branch="main"))["previous"] == "feature/y"


def test_tool_errors_come_back_to_the_agent_without_local_paths(git, repos):
    result = as_dict(_tool("git_checkout", git).func(repository="api", branch="nope"))

    assert "Branch non trovato" in result["error"] and "Repository disponibili: api, web." in result["error"]
    result = as_dict(_tool("git_push", git, project=None).func(repository="api"))
    assert "progetto" in result["error"]


def test_pull_all_tool_masks_repositories_and_authors(git, repos, masking_service):
    _push(repos, "second")
    pull_all = AgentMask(masking_service.session("Shop")).wrap([_tool("git_pull_all_by_branch", git)])[0]

    result = as_dict(pull_all.func(branch="main"))

    assert [o["status"] for o in result["repositories"]] == ["updated", "updated"]
    assert {(e.category.value, e.value) for e in masking_service.entries("Shop")} == {
        ("repository", "api"), ("repository", "web"), ("person", "Bob"), ("email", "bob@example.com"),
    }


def test_pull_all_tool_hides_local_paths(git, repos):
    _git(repos / "shop" / "web", "remote", "set-url", "origin", str(repos / "missing.git"))

    result = as_dict(_tool("git_pull_all_by_branch", git).func(branch="main"))

    failed = next(o for o in result["repositories"] if o["status"] == "failed")
    assert str(repos) not in failed["reason"]


# ------------------------------------------------------------- functions

def _function(name, git, project_data_service, step_input="", **params):
    context = FunctionContext(project_name="Shop", pipeline_input="", git=git, project_data=project_data_service)
    return FUNCTION_REGISTRY[name].execute(context, step_input, params)


def test_pull_all_function_uses_the_step_input_as_branch(git, repos, project_data_service):
    _local_develop(git, "api", "web")
    _push(repos, "on develop", branch="develop")

    result = _function("git_pull_all_repo_by_branch", git, project_data_service, step_input="develop\n")

    assert result.text.startswith("Branch develop su 2 repository: 2 aggiornato.")
    assert "- api (era su main): aggiornato, 1 commit nuovi" in result.text
    with pytest.raises(ValidationError, match="Indica il branch"):
        _function("git_pull_all_repo_by_branch", git, project_data_service)


def test_pull_all_function_fails_when_every_repository_fails(git, repos, project_data_service):
    for name in ("api", "web"):
        _git(repos / "shop" / name, "remote", "set-url", "origin", str(repos / "missing.git"))

    with pytest.raises(UpstreamError, match="Nessun repository aggiornato"):
        _function("git_pull_all_repo_by_branch", git, project_data_service, branch="main")


def test_fetch_function_on_every_repository(git, repos, project_data_service):
    _push(repos, "second")

    result = _function("git_fetch", git, project_data_service, repository="*")

    assert result.text.splitlines() == [
        "Fetch di 2 repository.",
        "- api · branch main · origin/main: 0 da pushare, 1 da pullare",
        "- web · branch main · origin/main: 0 da pushare, 1 da pullare",
    ]


def test_log_function_declares_the_authors(git, repos, project_data_service):
    _push(repos, "second")
    git.pull_fast_forward("Shop", "api")

    result = _function("git_log", git, project_data_service, repository="api", limit=5, author="bob")

    assert "Repository api · 1 commit:" in result.text and "Bob: second" in result.text
    assert [c.author for c in result.commits] == ["Bob"]
    with pytest.raises(ValidationError, match="limit"):
        _function("git_log", git, project_data_service, repository="api", limit=0)
