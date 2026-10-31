"""Function steps of the automations: the registry, validation on save, and
execution by the runner (real git repository in a tmp dir, fake agents)."""
import shutil
import subprocess

import pytest

from core.error import ValidationError
from fakes import FakeAgent
from function.registry import FUNCTION_REGISTRY
from function.spec import FunctionSpec, NoParams
from models.domain.pipeline import PipelineStep, RunStatus, StepAgent, StepKind
from models.domain.project import Project, ProjectSource
from service import agent_service as agent_service_module
from service.chat_service import ChatService
from service.pipeline_runner import PipelineRunner

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def project(tmp_path, project_store):
    """Project "shop" with a repository ``api`` holding two commits."""
    repo = tmp_path / "shop" / "api"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Ada")
    _git(repo, "config", "user.email", "ada@example.com")
    for message in ("first", "second"):
        (repo / "main.py").write_text(message, encoding="utf-8")
        _git(repo, "add", "main.py")
        _git(repo, "commit", "-q", "-m", message)
    project_store.save(Project(name="shop", source=ProjectSource.FOLDER, root_path=str(tmp_path / "shop")))
    return repo


@pytest.fixture
def service(project, monkeypatch, pipeline_service):
    monkeypatch.setattr(agent_service_module.AgentFactory, "create_agent",
                        staticmethod(lambda definition, client, tools: FakeAgent()))
    return pipeline_service


@pytest.fixture
def runner(store_service, monkeypatch, make_agent_service, git_service, project_data_service):
    chat = ChatService()
    monkeypatch.setattr(chat, "get_client", lambda model: object())
    git = git_service
    agents = make_agent_service(chat, git_service=git)
    return PipelineRunner(store_service, agents, git, project_data_service)


@pytest.fixture
def masking(masking_service):
    return masking_service


@pytest.fixture
def masked_runner(store_service, masking, monkeypatch, make_agent_service, git_service, project_data_service):
    """A runner that registers what the function steps declare sensitive."""
    chat = ChatService()
    monkeypatch.setattr(chat, "get_client", lambda model: object())
    git = git_service
    agents = make_agent_service(chat, git_service=git)
    return PipelineRunner(store_service, agents, git, project_data_service, masking_service=masking)


def _function(name="F", function="git_status", template="{input}", **params) -> PipelineStep:
    return PipelineStep(name=name, kind=StepKind.FUNCTION, function_name=function, params=params,
                        input_template=template)


def _run(service, runner, steps, pipeline_input=""):
    pipeline = service.create_pipeline("shop", "P", steps=steps)
    service.enqueue(pipeline.id, pipeline_input)
    return runner.run_next()


# ----------------------------------------------------------------- registry

def test_registry_keys_and_default_params():
    for name, spec in FUNCTION_REGISTRY.items():
        assert spec.name == name and spec.description
        spec.validate_params({})  # every parameter has a default


def test_invalid_params_name_the_field():
    with pytest.raises(ValidationError, match="title"):
        FUNCTION_REGISTRY["save_note"].validate_params({"title": 123})


# --------------------------------------------------------------- validation

@pytest.mark.parametrize("step, message", [
    (PipelineStep(name="F", kind=StepKind.FUNCTION), "Scegli la funzione"),
    (_function(function="missing"), "non esiste"),
    (_function(function="save_note", title=123), "title"),
])
def test_invalid_function_steps_rejected_on_save(service, step, message):
    with pytest.raises(ValidationError, match=message):
        service.create_pipeline("shop", "P", steps=[step])


# ---------------------------------------------------------------- execution

def test_function_feeds_the_next_agent_step(service, runner):
    run = _run(service, runner, [
        _function("Stato", repository="api"),
        PipelineStep(name="Riassumi", kind=StepKind.AGENT,
                     agent=StepAgent(system_prompt="Riassumi.", model="openai/gpt-4o")),
    ])

    assert run.status is RunStatus.DONE
    status, summary = run.steps
    assert status.output.startswith("Repository api") and "Nessun file modificato." in status.output
    assert status.agent_run_id is None
    assert summary.input == status.output and summary.agent_run_id is not None


def test_empty_repository_param_uses_the_step_input(service, runner):
    run = _run(service, runner, [_function()], pipeline_input="api")

    assert run.status is RunStatus.DONE and run.output.startswith("Repository api")


def test_git_status_function(service, runner, project):
    (project / "main.py").write_text("changed", encoding="utf-8")

    run = _run(service, runner, [_function(function="git_status", repository="api")])

    assert "1 file modificati" in run.output and "- main.py: modified, non staged" in run.output


def test_git_status_of_every_repository(service, masked_runner, masking, project):
    web = project.parent / "web"
    web.mkdir()
    _git(web, "init", "-q")
    (web / "app.js").write_text("nuovo", encoding="utf-8")
    broken = project.parent / "rotto"
    (broken / ".git").mkdir(parents=True)  # looks like a repository, git cannot read it

    run = _run(service, masked_runner, [_function(function="git_status", repository="*")])

    assert run.status is RunStatus.DONE and run.output.startswith("3 repository nel progetto.")
    assert "Repository api · branch" in run.output and "Nessun file modificato." in run.output
    assert "Repository web · branch" in run.output and "- app.js: untracked" in run.output
    assert "Repository rotto · stato non letto:" in run.output  # the others are still there
    assert sorted(entry.value for entry in masking.entries("shop")) == ["api", "rotto", "web"]


def test_git_status_of_every_repository_needs_one(service, runner, tmp_path, project_store):
    empty = tmp_path / "vuoto"
    empty.mkdir()
    project_store.save(Project(name="vuoto", source=ProjectSource.FOLDER, root_path=str(empty)))
    pipeline = service.create_pipeline("vuoto", "P", steps=[_function(function="git_status", repository="*")])
    service.enqueue(pipeline.id, "")

    run = runner.run_next()

    assert run.status is RunStatus.FAILED and "Nessun repository git" in run.steps[0].error


def test_save_note_function(service, runner, project_data_service):
    run = _run(service, runner, [_function(function="save_note", title="Report {date}")], pipeline_input="Testo")

    assert run.status is RunStatus.DONE and run.output.startswith("Nota salvata: Report ")
    [note] = project_data_service.list_notes("shop")
    assert note.name.startswith("Report ") and project_data_service.read_note("shop", note.name) == "Testo"


def test_function_steps_register_the_values_they_declare_sensitive(service, masked_runner, masking):
    """Only functions, no agent (which would register the repositories itself):
    git_status declares its repository, save_note declares nothing."""
    run = _run(service, masked_runner, [_function("Stato", repository="api"), _function("Nota", function="save_note")])

    assert run.status is RunStatus.DONE
    assert [(entry.category.value, entry.value) for entry in masking.entries("shop")] == [("repository", "api")]


def test_function_error_fails_the_step_with_its_message(service, runner):
    run = _run(service, runner, [_function(repository="nope")])

    assert run.status is RunStatus.FAILED and "Cartella inesistente" in run.steps[0].error


def test_unexpected_exception_fails_the_step(service, runner, monkeypatch):
    def boom(context, step_input, params):
        raise RuntimeError("kaboom")

    broken = FunctionSpec(name="broken", description="x", params=NoParams, run=boom)
    monkeypatch.setitem(FUNCTION_REGISTRY, "broken", broken)

    run = _run(service, runner, [_function(function="broken")])

    assert run.status is RunStatus.FAILED and run.steps[0].error == "errore imprevisto: kaboom"
