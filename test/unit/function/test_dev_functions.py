"""Blocco 09: the functions of «Prepara sviluppo» (git_check_clean,
git_checkout_branches) and «Verifica sviluppo» (clean_mbare_pilot, run_tests)
on real repositories (needs ``git``): a bare "origin" and the project "Shop"
with the clones ``api`` and ``lib``."""
import shutil
import subprocess

import pytest

from core.error import ConflictError, NotFoundError, ValidationError
from domain.client.command.client import CommandClient, CommandResult
from domain.dev import tests
from domain.dev.inputs import parse_prepare, parse_verify, render_prepare, render_verify
from domain.project import code_todos
from function.context import FunctionContext
from function.registry import FUNCTION_REGISTRY
from models.domain.dev import PrepareTarget, TestKind, TestScope
from models.domain.project import Project, ProjectSource

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _git(cwd, *args) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def _identity(repo):
    _git(repo, "config", "user.name", "Ada")
    _git(repo, "config", "user.email", "ada@example.com")


def _commit(repo, message, file="main.py", text=None):
    (repo / file).parent.mkdir(parents=True, exist_ok=True)
    (repo / file).write_text(text if text is not None else message, encoding="utf-8")
    _git(repo, "add", file)
    _git(repo, "commit", "-q", "-m", message)


@pytest.fixture
def shop(tmp_path, project_store):
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "-q", "-b", "main")
    _identity(seed)
    _commit(seed, "first")
    _git(seed, "branch", "develop")
    _git(tmp_path, "clone", "-q", "--bare", str(seed), "origin.git")
    (tmp_path / "shop").mkdir()
    for name in ("api", "lib"):
        _git(tmp_path / "shop", "clone", "-q", str(tmp_path / "origin.git"), name)
        _identity(tmp_path / "shop" / name)
    project_store.save(Project(name="Shop", source=ProjectSource.FOLDER, root_path=str(tmp_path / "shop")))
    return tmp_path


class FakeCommands(CommandClient):
    def __init__(self, returncode=0, output="3 passed"):
        self.calls: list[tuple[str, list[str]]] = []
        self._result = CommandResult(returncode, output)

    def run(self, cwd, arguments, timeout_seconds):
        self.calls.append((cwd.name, arguments))
        return self._result


def _context(git_service, project_data_service, pipeline_input, commands=None):
    return FunctionContext(project_name="Shop", pipeline_input=pipeline_input, git=git_service, project_data=project_data_service,
                           commands=commands or FakeCommands())


def _call(name, context, params=None):
    return FUNCTION_REGISTRY[name].execute(context, "", params or {})


# ------------------------------------------------------------------ inputs

def test_the_inputs_round_trip():
    targets = [PrepareTarget(repository="api", branch="feature/x", base="develop"), PrepareTarget(branch="main")]
    assert render_prepare(targets) == "api feature/x develop\n. main"
    assert parse_prepare(render_prepare(targets)) == targets
    assert render_verify("", "agent-task-a.md", TestScope.TOUCHED) == ". agent-task-a.md touched"
    assert parse_verify("api agent-task-a.md") == ("api", "agent-task-a.md", TestScope.ALL)
    for wrong in ("", "api", "a b c d"):
        with pytest.raises(ValidationError):
            parse_prepare(wrong)
    with pytest.raises(ValidationError):
        parse_verify("api task maybe")


# ----------------------------------------------------------- preparation

def test_check_clean_stops_on_changes(shop, git_service, project_data_service):
    context = _context(git_service, project_data_service, "api main\nlib main")
    (shop / "shop" / "lib" / "nuovo.txt").write_text("untracked is fine", encoding="utf-8")
    assert "nessuna modifica" in _call("git_check_clean", context).text

    (shop / "shop" / "api" / "main.py").write_text("changed", encoding="utf-8")
    with pytest.raises(ConflictError, match="api: main.py"):
        _call("git_check_clean", context)


def test_checkout_branches_switches_creates_and_pulls(shop, git_service, project_data_service):
    pusher = shop / "pusher"
    _git(shop, "clone", "-q", str(shop / "origin.git"), "pusher")
    _identity(pusher)
    _git(pusher, "switch", "-q", "develop")
    _commit(pusher, "on develop")
    _git(pusher, "push", "-q", "origin", "develop")

    text = _call("git_checkout_branches", _context(git_service, project_data_service, "api develop\nlib feature/login develop")).text

    assert "- api: su develop, già aggiornato" in text  # created from origin/develop after the fetch
    assert "- lib: creato feature/login da origin/develop" in text
    assert git_service.status("Shop", "api").branch == "develop"
    assert git_service.status("Shop", "lib").branch == "feature/login"
    _commit(pusher, "again on develop", "other.py")
    _git(pusher, "push", "-q", "origin", "develop")
    assert "aggiornato (1 commit)" in _call("git_checkout_branches", _context(git_service, project_data_service, "api develop")).text
    assert "senza upstream" in _call("git_checkout_branches", _context(git_service, project_data_service, "lib feature/login")).text


def test_checkout_branches_stops_at_the_first_problem(shop, git_service, project_data_service):
    with pytest.raises(ConflictError, match="lib non preparato: il branch nuovo non c'è") as error:
        _call("git_checkout_branches", _context(git_service, project_data_service, "api main\nlib nuovo"))
    assert "- api: su main" in str(error.value)  # what was done before
    with pytest.raises(ConflictError, match="base manca non c'è"):
        _call("git_checkout_branches", _context(git_service, project_data_service, "api altro manca"))
    _git(shop / "shop" / "lib", "switch", "-q", "-c", "locale")
    assert "creato da-locale da locale" in _call(
        "git_checkout_branches", _context(git_service, project_data_service, "lib da-locale locale")).text
    assert NotFoundError  # imported for the error kinds above


# ---------------------------------------------------------- verification

def test_clean_removes_the_task_folder_and_the_comment_lines(shop, git_service, project_data_service):
    api = shop / "shop" / "api"
    (api / "mbare-pilot" / "agent-task-login").mkdir(parents=True)
    (api / "mbare-pilot" / "agent-task-login" / "task.md").write_text("# Login", encoding="utf-8")
    (api / "main.py").write_bytes(b"x = 1\r\n    # todoMbarePilot{rifare}\r\ny = 2  # todoMbarePilot{anche qui}\r\n")
    (api / "logo.bin").write_bytes(b"\xff\xfe\x00")

    text = _call("clean_mbare_pilot", _context(git_service, project_data_service, "api agent-task-login.md")).text

    assert "- cartella mbare-pilot/agent-task-login: tolta" in text
    assert "tolti 1" in text and "main.py:3" in text
    assert not (api / "mbare-pilot").exists()
    assert (api / "main.py").read_bytes() == b"x = 1\r\ny = 2  # todoMbarePilot{anche qui}\r\n"  # CRLF kept
    again = _call("clean_mbare_pilot", _context(git_service, project_data_service, "api agent-task-login.md"), {"remove_todos": False}).text
    assert again == "Pulizia:\n- cartella mbare-pilot/agent-task-login: non c'era"


def test_strip_keeps_other_lines():
    text = "<!-- todoMbarePilot{a} -->\n/* todoMbarePilot{b} */\n-- todoMbarePilot{c}\nkeep\n"
    assert code_todos.strip(text) == ("keep\n", 3, [])


def test_run_tests_all_touched_and_failed(shop, git_service, project_data_service):
    api = shop / "shop" / "api"
    _commit(api, "py", "pyproject.toml", "[project]\nname='api'\n")
    _commit(api, "src", "app/login.py", "x = 1\n")
    _commit(api, "test", "tests/test_login.py", "def test(): pass\n")
    _commit(api, "other", "tests/test_other.py", "def test(): pass\n")
    commands = FakeCommands()

    assert "Test tutti: ok (`pytest`)" in _call("run_tests", _context(git_service, project_data_service, "api t.md all", commands)).text
    assert "nessun test toccato" in _call("run_tests", _context(git_service, project_data_service, "api t.md touched", commands)).text
    (api / "app" / "login.py").write_text("x = 2\n", encoding="utf-8")
    assert "solo toccati (1)" in _call("run_tests", _context(git_service, project_data_service, "api t.md touched", commands)).text
    assert commands.calls[-1] == ("api", ["pytest", "tests/test_login.py"])

    project_data_service.save_test_settings("Shop", TestScope.ALL, {"api": "uv run pytest -q"})
    failing = FakeCommands(1, "....\nFAILED tests/test_login.py::test - assert 1 == 2\nE   assert 1 == 2\n1 failed")
    with pytest.raises(ConflictError, match="Test falliti") as error:
        _call("run_tests", _context(git_service, project_data_service, "api t.md", failing))
    assert "FAILED tests/test_login.py::test" in str(error.value) and "uv run pytest -q" in str(error.value)

    project_data_service.save_test_settings("Shop", TestScope.ALL, {"api": "pytest 'unclosed"})
    with pytest.raises(ValidationError, match="non valido"):
        _call("run_tests", _context(git_service, project_data_service, "api t.md", commands))
    assert "non lo riconosco" in _call("run_tests", _context(git_service, project_data_service, "lib t.md", commands)).text


# ----------------------------------------------------------------- tests

def test_detect_and_default_commands():
    assert tests.detect({"pom.xml", "mvnw"}) is TestKind.MAVEN
    assert tests.default_command(TestKind.MAVEN, {"pom.xml", "mvnw"}, windows=False) == "./mvnw -B test"
    assert tests.default_command(TestKind.MAVEN, {"pom.xml", "mvnw", "mvnw.cmd"}, windows=True) == "mvnw.cmd -B test"
    assert tests.default_command(TestKind.MAVEN, {"pom.xml"}) == "mvn -B test"
    assert tests.detect({"pyproject.toml", "uv.lock"}) is TestKind.PYTHON
    assert tests.default_command(TestKind.PYTHON, {"pyproject.toml", "uv.lock"}) == "uv run pytest"
    assert tests.detect({"package.json"}) is TestKind.NODE and tests.default_command(TestKind.NODE, set()) == "npm test"
    assert tests.detect({"README.md"}) is TestKind.UNKNOWN and tests.default_command(TestKind.UNKNOWN, set()) == ""


def test_touched_tests_and_commands():
    java = ["src/main/java/a/Login.java", "src/test/java/a/LoginTest.java", "src/test/java/a/LoginIT.java", "src/test/java/a/OtherTest.java"]
    assert tests.touched_tests(TestKind.MAVEN, ["src/main/java/a/Login.java"], java) == ["LoginTest", "LoginIT"]
    assert tests.command("mvn -B test", TestKind.MAVEN, ["LoginTest"]) == [
        "mvn", "-B", "test", "-Dtest=LoginTest", "-Dsurefire.failIfNoSpecifiedTests=false"]
    node = ["src/login.ts", "src/login.test.ts", "src/other.spec.tsx", "README.md"]
    assert tests.touched_tests(TestKind.NODE, ["src/login.ts", "src/other.spec.tsx", "README.md"], node) == ["src/login.test.ts", "src/other.spec.tsx"]
    assert tests.command("npm test", TestKind.NODE, ["a.test.ts"]) == ["npm", "test", "--", "a.test.ts"]
    assert tests.command("npm test --", TestKind.NODE, ["a.test.ts"]) == ["npm", "test", "--", "a.test.ts"]
    assert tests.command("pytest", TestKind.PYTHON, []) == ["pytest"]
    assert tests.touched_tests(TestKind.PYTHON, ["app/x.py"], ["app/x_test.py", "tests/test_x.py"]) == ["app/x_test.py", "tests/test_x.py"]
    assert tests.touched_tests(TestKind.UNKNOWN, ["a"], ["a"]) == [] and not tests.is_test_file(TestKind.UNKNOWN, "a")


def test_commands_split_as_the_system_does():
    windows = r'D:\a\venv\python.exe -c "print(1); raise SystemExit(1)" -k ' + "'x y'"
    assert tests.split(windows, windows=True) == [r"D:\a\venv\python.exe", "-c", "print(1); raise SystemExit(1)", "-k", "x y"]
    assert tests.split("pytest -k 'a b' tests/x\\ y.py", windows=False) == ["pytest", "-k", "a b", "tests/x y.py"]
    assert tests.command(r"C:\mvn\mvn.cmd -B test", TestKind.MAVEN, ["ATest"], windows=True)[0] == r"C:\mvn\mvn.cmd"
    with pytest.raises(ValueError):
        tests.split("pytest 'unclosed", windows=True)


def test_failures_per_tool():
    maven = "[INFO] x\n[ERROR] Tests run: 3, Failures: 1\n[ERROR]   LoginTest.ok:12 expected\n[ERROR] \n[ERROR] To see the full stack trace\n"
    assert tests.failures(TestKind.MAVEN, maven) == ["[ERROR] Tests run: 3, Failures: 1", "[ERROR]   LoginTest.ok:12 expected"]
    node = " PASS a\n FAIL src/login.test.ts\n  ● login › works\n"
    assert tests.failures(TestKind.NODE, node) == [" FAIL src/login.test.ts", "  ● login › works"]
    assert tests.failures(TestKind.UNKNOWN, "a\n\nb\n") == ["a", "b"]  # the tail
    many = "\n".join(f"FAILED t{i}" for i in range(50))
    assert tests.failures(TestKind.PYTHON, many)[-1] == "… e altre 10 righe"


def test_the_command_client(tmp_path):
    import sys

    from core.error import UpstreamError

    client = CommandClient()
    result = client.run(tmp_path, [sys.executable, "-c", "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)"], 30)
    assert result.returncode == 3 and "out" in result.output and "err" in result.output
    with pytest.raises(UpstreamError, match="non è finito"):
        client.run(tmp_path, [sys.executable, "-c", "import time; time.sleep(5)"], 1)
    with pytest.raises(UpstreamError, match="Impossibile eseguire"):
        client.run(tmp_path, ["definitely-not-a-command-xyz"], 5)
