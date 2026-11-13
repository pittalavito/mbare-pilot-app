"""Plan 11, from an agent to an automation: the Operator's commands (allowed,
asked, granted), its tools, the ``tool`` steps with named fields, the draft
of an automation from a run's trace and the learned preparation at the
delegation, on real repositories."""
import json
import shutil

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.container import Container
from core.error import ConflictError, NotFoundError, ValidationError
from domain.chat.chatbots_default import DEFAULT_CHATBOTS, OPERATOR_JAVA
from domain.client.command.client import CommandResult
from domain.dev import tests
from domain.pipeline import yaml_format
from domain.pipeline.graph import linear_edges
from models.domain.agent import AgentRunRecord, GenerationRecord, RunTelemetry, TokenSummary, ToolCallRecord
from models.domain.chatbot import KIND_TOOLS, ChatbotKind, ChatMessage, Conversation, MessageRole
from models.domain.dev import LearnedPreparation, TestKind
from models.domain.learn import LearnedStep, LearnRequest
from models.domain.masking import MaskCategory
from models.domain.pipeline import AutomationPurpose, Pipeline, PipelineRun, PipelineStep, RunStatus, StepKind
from service.command_service import CommandService, normalize
from service.dev_checks_service import DevChecksService
from service.git_service import GitService
from service.learn_service import EXPIRED, LearnService
from service.pipeline_runner import PipelineRunner
from tool.context import ToolContext
from tool.registry import TOOL_REGISTRY
from unit.service.test_copilot_service import _git, _service, _task, data, project  # noqa: F401 (fixtures)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


class FakeCommands:
    """Records the commands instead of running them."""

    def __init__(self, returncode=0, output="BUILD SUCCESS"):
        self.calls: list[tuple[str, list[str]]] = []
        self.returncode, self.output = returncode, output

    def run(self, cwd, arguments, timeout_seconds):
        self.calls.append((cwd.name, arguments))
        return CommandResult(returncode=self.returncode, output=self.output)


@pytest.fixture
def commands(project, stores):  # noqa: F811
    fake = FakeCommands()
    return CommandService(stores.projects, GitService(stores.projects), fake), fake


def _tool(name, context):
    return TOOL_REGISTRY[name].build(context)


# ------------------------------------------------------------------ commands

def test_only_allowed_commands_run_the_others_wait_for_the_users_answer(commands):
    service, fake = commands
    assert service.save_allowed("acme", ["  mvn   -B clean install ", "", "mvn -B clean install"]) == ["mvn -B clean install"]

    assert service.run("acme", "api", "mvn -B  clean install").ok
    assert fake.calls[0][0] == "api" and fake.calls[0][1][1:] == ["-B", "clean", "install"]

    refused = service.run("acme", "web", "mvn -X install")
    assert not refused.allowed and not refused.ok and len(fake.calls) == 1
    service.run("acme", "web", "mvn -X install")  # asked again: one request only
    assert [(item.repository, item.command) for item in service.requests("acme")] == [("web", "mvn -X install")]

    service.answer("acme", "mvn -X install", allow=True)  # «Solo stavolta»
    assert service.requests("acme") == [] and service.run("acme", "web", "mvn -X install").ok
    assert not service.run("acme", "web", "mvn -X install").allowed  # the grant is used up

    service.answer("acme", "mvn -X install", allow=True, always=True)  # «Sempre»
    assert "mvn -X install" in service.allowed("acme")
    service.run("acme", "api", "rm -rf .")
    service.answer("acme", "rm -rf .", allow=False)  # «No»
    assert service.requests("acme") == [] and "rm -rf ." not in service.allowed("acme")
    with pytest.raises(NotFoundError):
        service.answer("acme", "rm -rf .", allow=True)
    with pytest.raises(ValidationError):
        service.run("acme", "api", "   ")
    with pytest.raises(NotFoundError):
        service.allowed("nessuno")


def test_saving_the_list_answers_the_requests_it_allows_and_the_output_is_its_tail(commands):
    service, fake = commands
    service.run("acme", "api", "npm ci")
    service.save_allowed("acme", ["npm ci"])
    assert service.requests("acme") == []
    fake.output = "\n".join(f"riga {number}" for number in range(100)) + "\n\n"
    assert service.run("acme", "api", "npm ci").output.splitlines() == [f"riga {number}" for number in range(70, 100)]
    fake.returncode = 1
    assert not service.run("acme", "api", "npm ci").ok


def test_the_detected_install_and_test_commands_are_suggested(commands, project):  # noqa: F811
    service, _ = commands
    (project / "api" / "pom.xml").write_text("<project/>", encoding="utf-8")
    (project / "web" / "uv.lock").write_text("", encoding="utf-8")
    (project / "web" / "pyproject.toml").write_text("", encoding="utf-8")
    suggested = service.suggested("acme")
    assert any(command.endswith("-B clean install") for command in suggested) and "uv sync" in suggested
    assert "uv run pytest" in suggested
    service.save_allowed("acme", ["uv sync"])
    assert "uv sync" not in service.suggested("acme")
    assert tests.install_command(TestKind.NODE, {"package-lock.json"}) == "npm ci"
    assert tests.install_command(TestKind.NODE, set()) == "npm install"
    assert tests.install_command(TestKind.PYTHON, set()) == "" and tests.install_command(TestKind.UNKNOWN, set()) == ""
    assert tests.install_command(TestKind.MAVEN, {"mvnw"}, windows=False) == "./mvnw -B clean install"
    assert normalize(" a  b ") == "a b"


# --------------------------------------------------------------------- tools

def test_run_command_tool_runs_refuses_and_reports_a_failure(commands, git_service):
    service, fake = commands
    context = ToolContext(project_name="acme", git=git_service, commands=service)
    run = _tool("run_command", context)
    service.save_allowed("acme", ["mvn -B clean install"])

    assert run(repository="api", command="mvn -B clean install").exit_code == 0
    refused = run(repository="api", command="mvn deploy")
    assert "non permesso" in refused.error and "mvn deploy" in refused.error
    fake.returncode = 2
    assert "uscito con codice 2" in run(repository="api", command="mvn -B clean install").error
    assert "Repository disponibili" in run(repository="nessuno", command="mvn -B clean install").error
    assert "comandi del progetto" in _tool("run_command", ToolContext(project_name="acme", git=git_service))(repository="api", command="x").error


def test_the_pom_tool_compares_the_poms_with_the_parent(project, git_service):  # noqa: F811
    pom = "<project><modelVersion>4.0.0</modelVersion><groupId>g</groupId><artifactId>{a}</artifactId><version>{v}</version>{p}</project>"
    (project / "api" / "pom.xml").write_text(pom.format(a="api-parent-lib", v="2.0.0", p=""), encoding="utf-8")
    parent = "<parent><groupId>g</groupId><artifactId>api-parent-lib</artifactId><version>1.0.0</version></parent>"
    (project / "web" / "pom.xml").write_text(pom.format(a="web", v="1.0.0", p=parent), encoding="utf-8")
    result = _tool("maven_parent_alignment", ToolContext(project_name="acme", git=git_service))(parent_artifact_id="", property="")
    assert "1 da allineare" in result.text and "1.0.0 → 2.0.0" in result.text
    assert "progetto" in _tool("maven_parent_alignment", ToolContext(project_name=None, git=git_service))(parent_artifact_id="", property="").error


def test_the_operator_is_a_default_chatbot_with_fixed_tools():
    [operator] = [bot for bot in DEFAULT_CHATBOTS if bot.kind is ChatbotKind.OPERATOR]
    assert operator.name == OPERATOR_JAVA and "run_command" in KIND_TOOLS[ChatbotKind.OPERATOR]
    assert not {"git_commit", "git_push"} & set(KIND_TOOLS[ChatbotKind.OPERATOR])
    assert all(name in TOOL_REGISTRY for name in KIND_TOOLS[ChatbotKind.OPERATOR])


# --------------------------------------------------------------- tool steps

def _learned(pipeline_store, *steps, fields=("branch", "base"), name="Prepara feature"):
    items = [PipelineStep(name=f"{position}. {tool}", kind=StepKind.TOOL, tool_name=tool, params=args)
             for position, (tool, args) in enumerate(steps, start=1)]
    return pipeline_store.save_pipeline(Pipeline(project_name="acme", name=name, steps=items, edges=linear_edges(items), fields=list(fields),
                                                 purpose=AutomationPurpose.PREPARE))


@pytest.fixture
def runner(stores, data, commands, masking_service):  # noqa: F811
    return PipelineRunner(stores.pipelines, None, GitService(stores.projects), data, masking_service, commands[0])  # type: ignore[arg-type]


def _run(runner, pipeline_store, pipeline, values):
    run = pipeline_store.save_pipeline_run(PipelineRun(pipeline_id=pipeline.id, input=json.dumps(values), status=RunStatus.RUNNING))
    return runner.execute(run)


def test_tool_steps_run_without_an_llm_with_the_fields_of_the_run(project, runner, pipeline_store, commands):  # noqa: F811
    service, fake = commands
    service.save_allowed("acme", ["mvn -B clean install"])
    base = _git(project / "api", "branch", "--show-current")
    pipeline = _learned(pipeline_store, ("git_create_branch", {"repository": "api", "name": "{in:branch}", "start_point": "{in:base}"}),
                        ("run_command", {"repository": "api", "command": "mvn -B clean install"}))

    run = _run(runner, pipeline_store, pipeline, {"branch": "feature/login", "base": base})
    assert run.status is RunStatus.DONE, run.error
    assert _git(project / "api", "branch", "--show-current") == "feature/login" and len(fake.calls) == 1
    assert json.loads(run.steps[0].output)["branch"] == "feature/login"

    failed = _run(runner, pipeline_store, pipeline, {"branch": "feature/login", "base": base})  # the branch exists now
    assert failed.status is RunStatus.FAILED and failed.error.startswith("Step 1 (1. git_create_branch)")
    missing = _run(runner, pipeline_store, pipeline, {"branch": "feature/x"})
    assert missing.status is RunStatus.FAILED and "Manca il valore di: base" in missing.error
    bad = pipeline_store.save_pipeline_run(PipelineRun(pipeline_id=pipeline.id, input="api feature/x", status=RunStatus.RUNNING))
    assert "oggetto JSON" in runner.execute(bad).error
    listed = pipeline_store.save_pipeline_run(PipelineRun(pipeline_id=pipeline.id, input="[1]", status=RunStatus.RUNNING))
    assert "oggetto JSON" in runner.execute(listed).error


def test_a_tool_step_with_wrong_arguments_or_a_removed_tool_fails(project, runner, pipeline_store):  # noqa: F811
    wrong = _learned(pipeline_store, ("git_fetch", {"repo": "api"}), fields=(), name="Sbagliata")
    assert "argomenti non validi" in _run(runner, pipeline_store, wrong, {}).error
    removed = _learned(pipeline_store, ("git_fetch", {"repository": "api"}), fields=(), name="Rimossa")
    removed.steps[0].tool_name = "non_esiste"
    pipeline_store.save_pipeline(removed)
    assert "non esiste" in _run(runner, pipeline_store, removed, {}).error


def test_tool_steps_and_fields_are_validated_and_go_through_yaml(project, pipeline_service):  # noqa: F811
    step = PipelineStep(name="Checkout", kind=StepKind.TOOL, tool_name="git_checkout", params={"repository": "api", "branch": "{in:branch}"})
    with pytest.raises(ValidationError, match="campi che l'automation non ha: branch"):
        pipeline_service.create_pipeline("acme", "Senza campi", steps=[step])
    with pytest.raises(ValidationError, match="non si può usare in uno step"):
        pipeline_service.create_pipeline("acme", "Push", steps=[step.model_copy(update={"tool_name": "git_push"})], fields=["branch"])
    with pytest.raises(ValidationError, match="stesso nome"):
        pipeline_service.create_pipeline("acme", "Doppi", steps=[step], fields=["branch", "branch"])
    saved = pipeline_service.create_pipeline("acme", "Checkout", steps=[step], fields=["branch"], purpose=AutomationPurpose.PREPARE)
    with pytest.raises(ValidationError, match="Manca il valore di: branch"):
        pipeline_service.enqueue(saved.id, "{}")
    assert pipeline_service.enqueue(saved.id, json.dumps({"branch": "develop"})).status is RunStatus.QUEUED

    text = pipeline_service.export_yaml(saved.id)
    assert "purpose: prepare" in text and "tool: git_checkout" in text and "'{in:branch}'" in text
    spec = yaml_format.parse(text)
    assert spec.fields == ["branch"] and spec.steps[0].args["branch"] == "{in:branch}"
    with pytest.raises(ValidationError, match="args vale solo con tool"):
        yaml_format.parse("name: X\nsteps:\n  - {name: A, function: git_status, args: {a: 1}}\n")
    updated = pipeline_service.save_yaml("acme", text.replace("  purpose: prepare\n", ""))
    assert updated.id == saved.id and updated.purpose is AutomationPurpose.NONE and updated.fields == ["branch"]


def test_the_definitions_sync_a_learned_automation(project, stores, config):  # noqa: F811
    folder = config.definitions_root / "project" / "acme"
    folder.mkdir(parents=True)
    (folder / "automation.yml").write_text(
        "automations:\n  - name: Prepara\n    purpose: prepare\n    fields: [branch]\n"
        "    steps:\n      - {name: Checkout, tool: git_checkout, args: {repository: api, branch: '{in:branch}'}}\n", encoding="utf-8")
    container = Container(stores=stores)
    assert {item.outcome.value for item in container.definition_service.sync("acme").items if item.name == "Prepara"} == {"created"}
    assert {item.outcome.value for item in container.definition_service.sync("acme").items if item.name == "Prepara"} == {"unchanged"}
    [pipeline] = [item for item in container.pipeline_service.list_pipelines("acme") if item.name == "Prepara"]
    assert pipeline.steps[0].kind is StepKind.TOOL and pipeline.purpose is AutomationPurpose.PREPARE


# ----------------------------------------------------------------- learning

def _call(name, arguments, result='{"ok": true}', ok=True):
    return ToolCallRecord(name=name, arguments=str(arguments), result=result, ok=ok)


@pytest.fixture
def taught(project, stores, masking_service, chatbot_store, run_store):  # noqa: F811
    """An Operator's answer whose run checked out a new branch (seen masked by the agent) and ran a build."""
    from models.domain.chatbot import Chatbot
    operator = chatbot_store.save_chatbot(Chatbot(project_name="acme", name="Op", kind=ChatbotKind.OPERATOR, system_prompt="x", model="mock/echo"))
    conversation = chatbot_store.save_conversation(Conversation(chatbot_id=operator.id, context="agent-task-login.md"))
    masking_service.register("acme", MaskCategory.REPOSITORY, "api")
    alias = masking_service.session("acme").mask("api")
    calls = [
        _call("git_status", {"repository": alias}),
        _call("git_create_branch", {"repository": alias, "name": "feature/login", "start_point": "develop"}),
        _call("git_checkout", {"repository": alias, "branch": "nessuno"}, result='{"error": "non esiste"}'),
        _call("run_command", {"repository": alias, "command": "mvn -B clean install"}),
        _call("git_fetch", {"repository": alias}, ok=False),
        _call("today", {}),
        _call("git_stash", "non un dizionario"),
        _call("git_stash_apply", "[1, 2]"),
    ]
    telemetry = RunTelemetry(tool_calls=calls, generations=[GenerationRecord(model="m", tokens=TokenSummary(cost_eur=0.0021), latency_ms=1)])
    run_store.save(AgentRunRecord(run_id="run-1", project_name="acme", config_name="Op", role_name="chatbot", prompt_id=0, prompt_version=1,
                                  model="m", telemetry=telemetry))
    message = chatbot_store.save_message(ChatMessage(conversation_id=conversation.id, role=MessageRole.ASSISTANT, content="Fatto.", run_id="run-1"))
    return message, conversation, alias


@pytest.fixture
def learn(stores, masking_service, pipeline_service):
    return LearnService(stores.chatbots, stores.runs, masking_service, pipeline_service)


def test_the_draft_has_the_successful_calls_with_real_values_and_proposes_the_fields(taught, learn):
    message, _, alias = taught
    draft = learn.draft(message.id)

    assert [step.tool for step in draft.steps] == ["git_status", "git_create_branch", "run_command"]
    assert draft.steps[0].read_only and not draft.steps[1].read_only
    assert draft.steps[1].args == {"repository": "api", "name": "feature/login", "start_point": "develop"}  # not the alias
    assert {value.value: value.field for value in draft.values} == {"api": "", "feature/login": "branch", "develop": "base"}
    assert draft.cost_eur == 0.0021 and draft.run_id == "run-1" and alias not in json.dumps(draft.model_dump())


def test_saving_the_draft_makes_an_automation_with_fields(taught, learn):
    message, _, _ = taught
    draft = learn.draft(message.id)
    request = LearnRequest(name="Prepara feature", purpose=AutomationPurpose.PREPARE, steps=draft.steps[1:],
                           fields={"feature/login": "branch", "develop": "base", "": "x", "api": ""})
    pipeline = learn.save("acme", request)
    assert pipeline.fields == ["branch", "base"] and pipeline.purpose is AutomationPurpose.PREPARE
    assert pipeline.steps[0].name == "1. git_create_branch"
    assert pipeline.steps[0].params == {"repository": "api", "name": "{in:branch}", "start_point": "{in:base}"}
    assert pipeline.steps[1].params["command"] == "mvn -B clean install"
    with pytest.raises(ValidationError, match="non si possono ripetere"):
        learn.save("acme", LearnRequest(name="Push", steps=[LearnedStep(tool="git_push", args={"items": [{"a": "api"}, 1]})]))


def test_a_task_value_becomes_the_task_field_and_an_expired_or_empty_run_says_so(taught, learn, chatbot_store, run_store):
    message, conversation, alias = taught
    run_store.save(AgentRunRecord(run_id="run-2", project_name="acme", config_name="Op", role_name="chatbot", prompt_id=0, prompt_version=1,
                                  model="m", telemetry=RunTelemetry(tool_calls=[
                                      _call("git_stash", {"repository": alias, "message": "agent-task-login.md"}),
                                      _call("git_status", {"repository": alias})])))
    second = chatbot_store.save_message(ChatMessage(conversation_id=conversation.id, role=MessageRole.ASSISTANT, content="ok", run_id="run-2"))
    assert {value.value: value.field for value in learn.draft(second.id).values}["agent-task-login.md"] == "task"

    run_store.save(AgentRunRecord(run_id="run-3", project_name="acme", config_name="Op", role_name="chatbot", prompt_id=0, prompt_version=1,
                                  model="m", telemetry=RunTelemetry(tool_calls=[_call("git_status", {"repository": alias})])))
    only_reads = chatbot_store.save_message(ChatMessage(conversation_id=conversation.id, role=MessageRole.ASSISTANT, content="ok", run_id="run-3"))
    with pytest.raises(ValidationError, match="niente da salvare"):
        learn.draft(only_reads.id)
    expired = chatbot_store.save_message(ChatMessage(conversation_id=conversation.id, role=MessageRole.ASSISTANT, content="ok", run_id="gone"))
    with pytest.raises(NotFoundError, match="scaduta") as error:
        learn.draft(expired.id)
    assert str(error.value) == EXPIRED
    with pytest.raises(NotFoundError):
        learn.draft(9999)
    orphan = chatbot_store.save_message(ChatMessage(conversation_id=conversation.id, role=MessageRole.ASSISTANT, content="ok", run_id="run-2"))
    chatbot_store.delete_conversation(conversation.id)
    with pytest.raises(NotFoundError):
        learn.draft(orphan.id)


# --------------------------------------------------------------- delegation

def test_the_delegation_runs_a_learned_preparation_with_the_fields_of_the_task(project, data, stores, pipeline_store, copilot_store,  # noqa: F811
                                                                               commands):
    git = GitService(stores.projects)
    checks = DevChecksService(stores.pipelines, PipelineRunner(stores.pipelines, None, git, data, None, commands[0]), git, data)  # type: ignore[arg-type]
    service = _service(stores, data)
    service.use_dev_checks(checks)
    base = _git(project / "api", "branch", "--show-current")
    pipeline = _learned(pipeline_store, ("git_create_branch", {"repository": "api", "name": "{in:branch}", "start_point": "{in:base}"}))
    note = _task(data)

    session = service.start("acme", note, "api", learned=LearnedPreparation(automation_id=pipeline.id,
                                                                            fields={"branch": "feature/login", "base": base, "extra": "x"}))
    first = service.messages(session.id)[0].content
    assert first.startswith("🧰 Preparazione ok.") and "✓ 1. git_create_branch" in first
    assert _git(project / "api", "branch", "--show-current") == "feature/login"

    with pytest.raises(ConflictError, match="Preparazione non riuscita, Copilot non è partito."):
        service.start("acme", note, "api", learned=LearnedPreparation(automation_id=pipeline.id, fields={"branch": "feature/login", "base": base}))
    assert len(copilot_store.list_sessions("acme")) == 1
    with pytest.raises(NotFoundError):
        checks.prepare_learned("acme", 9999, {})
    pipeline_store.save_pipeline(pipeline.model_copy(update={"active": False}))
    with pytest.raises(ValidationError, match="disattivata"):
        checks.prepare_learned("acme", pipeline.id, {})


# ---------------------------------------------------------------------- API

def test_the_api_saves_the_commands_and_the_operator_answers_requests_and_promotes(project, stores, taught):  # noqa: F811
    message, _, _ = taught
    container = Container(stores=stores)
    container.command_service._client = FakeCommands()
    with TestClient(create_app(container)) as client:
        operator = next(bot for bot in client.get("/projects/acme/chatbots").json() if bot["name"] == OPERATOR_JAVA)
        assert operator["kind"] == "operator" and "run_command" in operator["tool_names"]
        settings = client.put("/projects/acme/dev-settings", json={"allowed_commands": ["uv sync"], "operator_chatbot_id": operator["id"]}).json()
        assert settings["allowed_commands"] == ["uv sync"] and settings["operator_chatbot_id"] == operator["id"]
        assert "suggested_commands" in client.get("/projects/acme/dev-settings").json()
        assert client.put("/projects/acme/dev-settings", json={}).json()["allowed_commands"] == ["uv sync"]  # None = unchanged

        container.command_service.run("acme", "api", "mvn verify")
        assert client.get("/projects/acme/command-requests").json() == [{"repository": "api", "command": "mvn verify"}]
        assert client.post("/projects/acme/command-requests/answer", json={"command": "mvn verify", "allow": True, "always": True}).status_code == 204
        assert client.get("/projects/acme/command-requests").json() == []
        assert client.post("/projects/acme/command-requests/answer", json={"command": "mvn verify", "allow": False}).status_code == 404

        draft = client.get(f"/messages/{message.id}/learn-draft").json()
        assert [step["tool"] for step in draft["steps"]] == ["git_status", "git_create_branch", "run_command"]
        saved = client.post("/projects/acme/pipelines/learned", json={
            "name": "Prepara", "purpose": "prepare", "steps": draft["steps"][1:], "fields": {"feature/login": "branch", "develop": "base"}})
        assert saved.status_code == 201 and saved.json()["fields"] == ["branch", "base"] and saved.json()["purpose"] == "prepare"
        assert saved.json()["steps"][0]["kind"] == "tool" and saved.json()["steps"][0]["tool_name"] == "git_create_branch"
        assert client.get("/messages/9999/learn-draft").status_code == 404
