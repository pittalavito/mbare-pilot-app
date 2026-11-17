"""Plan 18, the steps «Pianifica» and «Lavora»: the Pianificatore (one
structured call, fake model) proposes tasks for the items still uncovered,
creating makes them «to do» (also tasks written by hand), the path derives
each task's steps from its status and its Copilot session, the round
started with «Avvia» prepares, delegates, approves and runs the automation
after the verification; failed tests wait for the user."""
import shutil
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.container import Container
from core.error import ConflictError, NotFoundError, UpstreamError, ValidationError
from fakes import FakeStructuredClient
from models.domain.copilot import CopilotMessage, CopilotMessageRole, CopilotSession, CopilotSessionStatus
from models.domain.dev import VERIFY_FAILED, VERIFY_OK
from models.domain.note import Activity, ActivityStatus, NoteType, Reference, TaskStatus, TaskType, TodoItem
from models.domain.plan import PlanAnswer, PlanChoice, PlannedTask, PlanOptions, StepKey, StepState
from models.domain.rag import RagHit
from service.plan_service import PlanService, model_input
from service.today_service import TodayService
from unit.service.test_copilot_service import project  # noqa: F401 (fixture: acme with api and web)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

MODEL = "openai/gpt-4o"
ANSWER = PlanAnswer(tasks=[
    PlannedTask(title="Aggiorna la libreria", type=TaskType.DEVELOPMENT, repository="web", items=[], reason="serve prima",
                objective="Portare la libreria alla 2.0.", criteria=["build ok", " "]),
    PlannedTask(title="Login con OTP", type=TaskType.DEVELOPMENT, repository="api", items=[2, 3, 2, 9], reason="voci 2 e 3 insieme",
                objective="Il login chiede l'OTP.", criteria=["test verdi"]),
    PlannedTask(title="Analizza il flusso", type=TaskType.ANALYSIS, repository="nessuno", items=[1]),
    PlannedTask(title="  ", type=TaskType.JIRA),
])


class FakeRag:
    def __init__(self, error=None):
        self.error = error

    def search(self, project_name, question, limit):
        if self.error:
            raise self.error
        return [RagHit(path="context/arch.md", title="Architettura", section="Login", text="Il login   passa da auth.", score=0.9)][:limit]


class FakeCopilot:
    def __init__(self):
        self.list: list[CopilotSession] = []
        self.events: dict[int, list[str]] = {}
        self.started: list[dict] = []
        self.sent_back: list[tuple[int, str]] = []
        self.verified: list[int] = []
        self.fail_start: Exception | None = None
        self.approvals: list[int] = []
        self.unanswered: set[int] = set()

    def sessions(self, project_name):
        return self.list

    def session(self, session_id):
        return next(item for item in self.list if item.id == session_id)

    def start(self, project_name, task_note, repository="", prompt="", model="", prepare=None, learned=None):
        self.started.append({"task": task_note, "repository": repository, "prepare": prepare, "learned": learned})
        if self.fail_start:
            raise self.fail_start
        self.list.insert(0, _session(len(self.list) + 10, task_note, CopilotSessionStatus.PLANNING))

    def send_back(self, session_id, text):
        self.sent_back.append((session_id, text))
        self.list = [item.model_copy(update={"status": CopilotSessionStatus.QUEUED}) if item.id == session_id else item for item in self.list]

    def verify_again(self, session_id):
        self.verified.append(session_id)

    def approve(self, session_id):
        if session_id in self.unanswered:
            raise ConflictError("Copilot non ha ancora risposto")
        self.approvals.append(session_id)
        self.list = [item.model_copy(update={"status": CopilotSessionStatus.QUEUED}) if item.id == session_id else item for item in self.list]

    def session_turns(self, session_id):
        return [SimpleNamespace(usage=SimpleNamespace(ai_credits=0.5))]

    def messages(self, session_id):
        return [CopilotMessage(session_id=session_id, role=CopilotMessageRole.EVENT, content=text) for text in self.events.get(session_id, [])]


@pytest.fixture
def client():
    return FakeStructuredClient(ANSWER)


@pytest.fixture
def copilot():
    return FakeCopilot()


@pytest.fixture
def service(project, project_data_service, masking_service, structured_agent_service, stores, client, git_service, copilot,  # noqa: F811
            monkeypatch):
    monkeypatch.setattr(structured_agent_service._chat, "get_client", lambda model: client)
    return PlanService(project_data_service, masking_service, structured_agent_service, stores.plans, git_service,
                       FakeRag(), copilot, stores.pipelines)  # type: ignore[arg-type]


@pytest.fixture
def activity(project_data_service):
    return project_data_service.create_activity("acme", Activity(title="Login sicuro", description="OTP per tutti.", items=[
        TodoItem(text="Capire il flusso"), TodoItem(text="Chiedere l'OTP"), TodoItem(text="Mandare la mail"), TodoItem(text="Fatta", done=True),
    ]))


def test_the_pianificatore_proposes_the_tasks_from_one_masked_call(service, client, activity, run_store):
    plan = service.propose("acme", activity)

    call = client.calls[0]
    assert call["system_prompt"].startswith("Sei il Pianificatore") and call["output_cls"] is PlanAnswer
    assert "Riferimenti:" not in call["input"]
    assert "1. Capire il flusso" in call["input"] and "Fatta" not in call["input"] and "[Architettura · Login] Il login passa da auth." in call["input"]
    assert "api" not in call["input"].split("Repository:")[1].split("\n")[0]  # the repositories are masked
    assert [proposal.title for proposal in plan.proposals] == ["Aggiorna la libreria", "Login con OTP", "Analizza il flusso"]
    first, second, third = plan.proposals
    assert first.new and first.repository == "web" and first.criteria == ["build ok"]
    assert second.items == [2, 3] and second.item_texts == ["Chiedere l'OTP", "Mandare la mail"] and not second.new
    assert third.repository == "" and third.type is TaskType.ANALYSIS
    assert plan.tasks == [] and plan.paused and plan.prepare == "dev" and plan.cost_eur >= 0
    assert run_store.get_trace(plan.run_id) is not None
    assert service.path("acme", activity).plan.id == plan.id


def test_creating_makes_the_tasks_to_do_in_order_linked_to_their_items(service, activity, project_data_service):
    service.propose("acme", activity)
    plan = service.confirm("acme", activity, [
        PlanChoice(id=2, title="Login con OTP", type=TaskType.DEVELOPMENT, repository="api", objective=" Il login chiede l'OTP. ",
                   criteria=["test verdi", ""]),
        PlanChoice(id=1, title="Aggiorna la libreria 2.0", type=TaskType.DEVELOPMENT, repository="web", objective="Alla 2.0."),
        PlanChoice(title="Capire il flusso", type=TaskType.ANALYSIS, items=[1, 1, 2, 99]),  # by hand: item 2 is taken by now
    ])
    assert [item.repository for item in plan.tasks] == ["api", "web", ""] and plan.proposals == []
    login = project_data_service.agent_task("acme", plan.tasks[0].task)
    assert login.status is TaskStatus.TODO and login.objective == "Il login chiede l'OTP." and [c.text for c in login.criteria] == ["test verdi"]
    saved = project_data_service.activity("acme", activity)
    assert saved.status is ActivityStatus.IN_PROGRESS
    assert saved.items[1].agent_task == saved.items[2].agent_task == plan.tasks[0].task
    assert saved.items[4].text == "Aggiorna la libreria 2.0" and saved.items[4].agent_task == plan.tasks[1].task  # the new task's item
    assert saved.items[0].agent_task == plan.tasks[2].task
    assert set(saved.agent_tasks) >= {item.task for item in plan.tasks}
    with pytest.raises(ConflictError, match="non ha più: 1"):
        service.confirm("acme", activity, [PlanChoice(id=1, title="x", type=TaskType.DEVELOPMENT)])

    again = service.propose("acme", activity)  # «Proponi altri task»: the tasks stay
    assert len(again.tasks) == 3


def test_a_task_by_hand_without_any_call_and_dismissing(service, activity, project_data_service, stores, client):
    plan = service.confirm("acme", activity, [PlanChoice(title="A mano", type=TaskType.JIRA)])
    assert plan.run_id == "" and len(plan.tasks) == 1 and client.calls == []
    with pytest.raises(NotFoundError):
        service.dismiss("acme", "attivita-altra.md")
    with pytest.raises(ValidationError, match="almeno un task"):
        service.confirm("acme", activity, [])
    service.propose("acme", activity)
    today = TodayService(project_data_service, None, stores.plans).today("acme")
    assert [(item.kind.value, item.task) for item in today.waiting] == [("plan", activity)]
    assert service.waiting("acme")[0].activity == activity

    dismissed = service.dismiss("acme", activity)
    assert dismissed.proposals == [] and len(dismissed.tasks) == 1 and service.waiting("acme") == []


def test_an_item_that_changed_meanwhile_is_not_linked(service, activity, project_data_service):
    service.propose("acme", activity)
    saved = project_data_service.activity("acme", activity)
    items = [*saved.items]
    items[1] = items[1].model_copy(update={"text": "Chiedere l'OTP via SMS"})
    project_data_service.save_activity("acme", activity, saved.model_copy(update={"items": items}))
    plan = service.confirm("acme", activity, [PlanChoice(id=2, title="Login", type=TaskType.DEVELOPMENT)])
    after = project_data_service.activity("acme", activity)
    assert after.items[1].agent_task is None and after.items[2].agent_task == plan.tasks[0].task


def test_the_pianificatore_reads_the_titles_of_the_references(service, client, activity, project_data_service):
    reference = project_data_service.create_reference("acme", NoteType.CONTEXT_REFERENCE, Reference(title="Spec OTP", content="segreto"))
    current = project_data_service.activity("acme", activity)
    project_data_service.save_activity("acme", activity, current.model_copy(update={"references": [reference, "context-reference-sparito.md"]}))

    service.propose("acme", activity)

    assert "Riferimenti: Spec OTP\n" in client.calls[0]["input"] and "segreto" not in client.calls[0]["input"]


def test_a_failing_model_or_no_agent_is_reported(service, client, activity, agent_config_service, run_store):
    client.error = RuntimeError("quota")
    with pytest.raises(UpstreamError, match="quota"):
        service.propose("acme", activity)
    client.error, client.answer = None, None
    service._rag = FakeRag(error=ValidationError("indice vuoto"))
    assert service.propose("acme", activity).proposals == []  # an index that fails: no context, the call goes on
    service._rag = None
    client.answer = PlanAnswer()
    assert service.propose("acme", activity).proposals == []
    client.answer = SimpleNamespace(model_dump=lambda: {"tasks": [{"title": "Da dict", "type": "jira"}]})
    assert service.propose("acme", activity).proposals[0].title == "Da dict"
    agent_config_service.delete_config("pianificatore")
    with pytest.raises(NotFoundError):
        service.propose("acme", activity)


def _session(id_, task, status, **fields):
    return CopilotSession(id=id_, project_name="acme", task_note=task, repository="api", copilot_session_id="x", mcp_token="t", status=status, **fields)


def _states(path_task):
    return {step.key: step.state for step in path_task.steps}


def _created(service, activity, *choices):
    service.propose("acme", activity)
    return service.confirm("acme", activity, list(choices) or [
        PlanChoice(id=2, title="Login", type=TaskType.DEVELOPMENT, repository="api", objective="OTP"),
        PlanChoice(id=3, title="Analizza", type=TaskType.ANALYSIS, objective="Capire")])


def _plan(stores, activity):
    return stores.plans.latest("acme", activity)


def test_the_path_follows_each_task_through_its_steps(service, activity, project_data_service, copilot):
    plan = _created(service, activity)
    login, analysis = (item.task for item in plan.tasks)

    path = service.path("acme", activity)
    assert path.tasks[0].current and not path.tasks[1].current
    assert [step.key for step in path.tasks[0].steps][:2] == [StepKey.PREPARE, StepKey.DELEGATE]
    assert [step.key for step in path.tasks[1].steps] == [StepKey.DELEGATE, StepKey.ANSWER]

    copilot.list = [_session(4, login, CopilotSessionStatus.PLANNING)]
    states = _states(service.path("acme", activity).tasks[0])
    assert states[StepKey.DELEGATE] is StepState.DONE and states[StepKey.COPILOT_PLAN] is StepState.YOU and states[StepKey.EXECUTION] is StepState.TODO

    copilot.list = [_session(4, login, CopilotSessionStatus.RUNNING)]
    assert _states(service.path("acme", activity).tasks[0])[StepKey.EXECUTION] is StepState.RUNNING
    copilot.list = [_session(4, login, CopilotSessionStatus.DONE)]
    task = project_data_service.agent_task("acme", login)
    project_data_service.save_agent_task("acme", login, task.model_copy(update={"status": TaskStatus.TO_VERIFY}))
    copilot.events[4] = [f"{VERIFY_FAILED}\n\nStep 2", "altro"]
    states = _states(service.path("acme", activity).tasks[0])
    assert states[StepKey.VERIFY] is StepState.FAILED and states[StepKey.FINAL] is StepState.YOU
    copilot.events[4].append(VERIFY_OK)
    assert _states(service.path("acme", activity).tasks[0])[StepKey.VERIFY] is StepState.DONE
    copilot.events[4] = []
    assert _states(service.path("acme", activity).tasks[0])[StepKey.VERIFY] is StepState.SKIPPED
    copilot.list = [_session(4, login, CopilotSessionStatus.FAILED, error="crash")]
    failed = service.path("acme", activity).tasks[0]
    assert _states(failed)[StepKey.EXECUTION] is StepState.FAILED and next(step for step in failed.steps if step.key is StepKey.EXECUTION).detail == "crash"

    project_data_service.save_agent_task("acme", login, task.model_copy(update={"status": TaskStatus.DONE}))
    copilot.list = []
    path = service.path("acme", activity)
    assert all(step.state is StepState.DONE for step in path.tasks[0].steps) and path.tasks[1].current

    copilot.list = [_session(5, analysis, CopilotSessionStatus.PLANNING)]
    assert _states(service.path("acme", activity).tasks[1])[StepKey.ANSWER] is StepState.YOU
    copilot.list = [_session(5, analysis, CopilotSessionStatus.CANCELLED)]
    assert _states(service.path("acme", activity).tasks[1])[StepKey.ANSWER] is StepState.FAILED
    project_data_service.delete_note("acme", analysis)
    assert service.path("acme", activity).tasks[1].status == "missing"
    assert service.path("acme", "attivita-senza-piano.md").plan is None


def test_model_input_without_items_repositories_or_context():
    text = model_input(Activity(title="Vuota"), {}, [], [])
    assert "(nessuna)" in text and "Repository: (nessuno)" in text and "Contesto" not in text
    assert "(cartella del progetto)" in model_input(Activity(title="X"), {}, [""], [])


def test_the_round_starts_with_avvia_and_delegates_by_itself(service, activity, copilot, stores, project_data_service):
    plan = _created(service, activity)
    login = plan.tasks[0].task
    assert service.advance_all() == 0 and stores.plans.running() == []  # not started yet
    service.set_paused("acme", activity, False)

    assert service.advance_all() == 1
    assert copilot.started[0]["task"] == login and copilot.started[0]["repository"] == "api"
    assert copilot.started[0]["prepare"][0].branch.startswith("feature/")  # «Prepara sviluppo» by default
    states = _states(service.path("acme", activity).tasks[0])
    assert states[StepKey.PREPARE] is StepState.DONE and states[StepKey.COPILOT_PLAN] is StepState.YOU
    assert service.advance_all() == 0  # waits for the ok to Copilot's plan

    copilot.list = []
    task = project_data_service.agent_task("acme", login)
    project_data_service.save_agent_task("acme", login, task.model_copy(update={"status": TaskStatus.REFINEMENT}))
    assert service.advance_all() == 0  # moved back to refinement: the round waits


def test_the_preparation_follows_the_activitys_choice(service, activity, copilot, stores, pipeline_store, project):  # noqa: F811
    from domain.pipeline.graph import linear_edges
    from models.domain.pipeline import Pipeline, PipelineStep, StepKind
    step = PipelineStep(name="1. git_fetch", kind=StepKind.TOOL, tool_name="git_fetch", params={"repository": "api"})
    automation = pipeline_store.save_pipeline(Pipeline(project_name="acme", name="Prepara stack", steps=[step], edges=linear_edges([step]),
                                                       fields=["branch", "base", "extra"]))
    plan = _created(service, activity)
    login = plan.tasks[0].task
    service.set_paused("acme", activity, False)

    service.set_options("acme", activity, PlanOptions(prepare=f"automation:{automation.id}"))
    service.advance_all()
    started = copilot.started[0]["learned"]
    assert started.automation_id == automation.id and copilot.started[0]["prepare"] == []
    assert started.fields["branch"] == f"feature/{login.removeprefix('agent-task-').removesuffix('.md')}" and started.fields["extra"] == ""
    assert started.fields["base"]  # the repository's current branch

    copilot.list = []
    service.set_options("acme", activity, PlanOptions(prepare="none"))
    service.advance_all()
    assert copilot.started[1]["prepare"] == [] and copilot.started[1]["learned"] is None
    assert StepKey.PREPARE not in _states(service.path("acme", activity).tasks[0])
    for wrong in ("altro", "automation:999", "automation:x"):
        with pytest.raises(ValidationError, match="Preparazione non valida"):
            service.set_options("acme", activity, PlanOptions(prepare=wrong))


def test_a_failed_preparation_stops_until_retried_or_skipped(service, activity, copilot, stores):
    plan = _created(service, activity)
    login = plan.tasks[0].task
    service.set_paused("acme", activity, False)
    copilot.fail_start = ConflictError("Preparazione non riuscita, Copilot non è partito.\n\nModifiche non committate")

    service.advance_all()
    step = next(item for item in service.path("acme", activity).tasks[0].steps if item.key is StepKey.PREPARE)
    assert step.state is StepState.FAILED and "Modifiche non committate" in step.detail
    assert service.advance_all() == 0 and len(copilot.started) == 1  # stopped

    service.retry("acme", activity, login, StepKey.PREPARE)
    copilot.fail_start = UpstreamError("Copilot non c'è")
    service.advance_all()
    assert _states(service.path("acme", activity).tasks[0])[StepKey.DELEGATE] is StepState.FAILED
    service.retry("acme", activity, login, StepKey.DELEGATE)

    service.skip("acme", activity, login, StepKey.PREPARE)
    copilot.fail_start = None
    service.advance_all()
    assert copilot.started[-1]["prepare"] == [] and _states(service.path("acme", activity).tasks[0])[StepKey.PREPARE] is StepState.SKIPPED
    with pytest.raises(ValidationError, match="Non si può saltare"):
        service.skip("acme", activity, login, StepKey.DELEGATE)
    with pytest.raises(ValidationError, match="Non si può riprovare"):
        service.retry("acme", activity, login, StepKey.FINAL)
    with pytest.raises(NotFoundError):
        service.skip("acme", activity, "agent-task-altro.md", StepKey.PREPARE)


def test_failed_tests_wait_for_the_user(service, activity, copilot, stores, project_data_service):
    plan = _created(service, activity)
    login = plan.tasks[0].task
    service.set_paused("acme", activity, False)
    task = project_data_service.agent_task("acme", login)
    project_data_service.save_agent_task("acme", login, task.model_copy(update={"status": TaskStatus.TO_VERIFY}))
    copilot.list = [_session(4, login, CopilotSessionStatus.DONE)]
    copilot.events[4] = [f"{VERIFY_FAILED}\n\nFAILED test_login"]

    assert service.advance_all() == 0 and copilot.sent_back == []  # nothing goes back to Copilot by itself
    service.retry("acme", activity, login, StepKey.VERIFY)
    assert copilot.verified == [4]
    service.skip("acme", activity, login, StepKey.VERIFY)
    assert _states(service.path("acme", activity).tasks[0])[StepKey.VERIFY] is StepState.SKIPPED


def test_pause_and_controls_need_tasks(service, activity, copilot, stores):
    with pytest.raises(ConflictError, match="non ha ancora task"):
        service.set_paused("acme", activity, False)
    plan = _created(service, activity)
    service.set_paused("acme", activity, False)
    assert service.set_paused("acme", activity, True).paused
    assert service.advance_all() == 0 and stores.plans.running() == []
    assert service.advance(_plan(stores, activity)) == 0
    service.set_paused("acme", activity, False)
    assert service.advance_all() == 1
    with pytest.raises(ConflictError, match="da verificare"):
        copilot.list = []
        service.retry("acme", activity, plan.tasks[0].task, StepKey.VERIFY)


def test_one_broken_round_does_not_stop_the_others(service, activity, copilot, monkeypatch):
    _created(service, activity)
    service.set_paused("acme", activity, False)
    monkeypatch.setattr(service, "advance", lambda plan: (_ for _ in ()).throw(RuntimeError("rotto")))
    assert service.advance_all() == 0


def test_without_copilot_or_with_every_task_done_nothing_moves(service, activity, copilot, project_data_service, stores):
    plan = _created(service, activity, PlanChoice(id=2, title="Login", type=TaskType.DEVELOPMENT, objective="OTP"))
    service.set_paused("acme", activity, False)
    task = project_data_service.agent_task("acme", plan.tasks[0].task)
    project_data_service.save_agent_task("acme", plan.tasks[0].task, task.model_copy(update={"status": TaskStatus.DONE}))
    assert service.advance_all() == 0
    service._copilot = None
    assert service.advance(_plan(stores, activity)) == 0


def test_the_api_of_the_plan_and_of_the_round(project, stores, monkeypatch, project_data_service, default_chatbots):  # noqa: F811
    container = Container(stores=stores)
    monkeypatch.setattr(container.chat_service, "get_client", lambda model: FakeStructuredClient(ANSWER))
    activity = project_data_service.create_activity("acme", Activity(title="Login", items=[TodoItem(text="a"), TodoItem(text="b"), TodoItem(text="c")]))
    with TestClient(create_app(container)) as client:
        base = f"/projects/acme/activities/{activity}/plan"
        assert client.get(f"/projects/acme/activities/{activity}/path").json() == {"plan": None, "tasks": [], "summary": ""}
        assert client.post(f"{base}/pause", json={"paused": False}).status_code == 409
        assert len(client.post(base).json()["proposals"]) == 3
        assert client.get("/projects/acme/today").json()["waiting"][0]["kind"] == "plan"
        confirmed = client.post(f"{base}/confirm", json={"choices": [{"id": 2, "title": "Login", "type": "development", "objective": "o"},
                                                                     {"title": "A mano", "type": "jira", "items": [1]}]}).json()
        task = confirmed["tasks"][0]["task"]
        assert len(confirmed["tasks"]) == 2 and confirmed["proposals"] == []
        path = client.get(f"/projects/acme/activities/{activity}/path").json()
        assert path["tasks"][0]["steps"][0] == {"key": "prepare", "label": "Preparazione", "state": "todo", "detail": ""}
        assert client.post(f"{base}/pause", json={"paused": False}).json()["paused"] is False
        assert client.post(f"{base}/options", json={"prepare": "none", "auto_approve": True}).json()["auto_approve"] is True
        assert client.post(f"{base}/options", json={"prepare": "dev", "after_automation": 999}).status_code == 400
        assert client.post(f"{base}/skip", json={"task": task, "step": "prepare"}).json()["skipped"] == [f"{task}|prepare"]
        assert client.post(f"{base}/retry", json={"task": task, "step": "delegate"}).status_code == 200
        assert client.post(f"{base}/skip", json={"task": task, "step": "nope"}).status_code == 422
        client.post(base)
        assert client.post(f"{base}/dismiss").json()["proposals"] == []
        assert client.get(f"/projects/acme/activities/{activity}/path").json()["summary"] == ""


# -------------------------------------------------- automation after the verification

@pytest.fixture
def checks(service, stores, project_data_service, git_service):
    from service.dev_checks_service import DevChecksService
    from service.pipeline_runner import PipelineRunner
    runner = PipelineRunner(stores.pipelines, None, git_service, project_data_service)  # type: ignore[arg-type]
    checks = DevChecksService(stores.pipelines, runner, git_service, project_data_service)
    service.use_checks(checks)
    return checks


def _automation(pipeline_store, name, function, fields=(), params=None):
    from domain.pipeline.graph import linear_edges
    from models.domain.pipeline import Pipeline, PipelineStep, StepKind
    step = PipelineStep(name=function, kind=StepKind.TOOL, tool_name=function, params={"repository": "api", **(params or {})})
    return pipeline_store.save_pipeline(Pipeline(project_name="acme", name=name, steps=[step], edges=linear_edges([step]), fields=list(fields)))


def test_the_automation_after_the_verification_runs_by_itself(service, activity, copilot, stores, checks, pipeline_store,
                                                             project_data_service, project):  # noqa: F811
    after = _automation(pipeline_store, "Log", "git_log", fields=["branch"])
    plan = _created(service, activity)
    login = plan.tasks[0].task
    with pytest.raises(ValidationError, match="non trovata"):
        service.set_options("acme", activity, PlanOptions(after_automation=999))
    service.set_options("acme", activity, PlanOptions(prepare="none", after_automation=after.id))
    assert StepKey.AFTER not in _states(service.path("acme", activity).tasks[1])  # not for analysis tasks
    service.set_paused("acme", activity, False)
    assert service.advance_all() == 1 and copilot.started  # the delegation

    task = project_data_service.agent_task("acme", login)
    project_data_service.save_agent_task("acme", login, task.model_copy(update={"status": TaskStatus.TO_VERIFY}))
    copilot.list = [_session(4, login, CopilotSessionStatus.DONE)]
    copilot.events[4] = [VERIFY_OK]
    assert _states(service.path("acme", activity).tasks[0])[StepKey.AFTER] is StepState.TODO
    assert service.advance_all() == 1  # the automation after, with its fields from the task
    assert '"branch": "feature/' in pipeline_store.list_pipeline_runs(after.id)[0].input
    states = _states(service.path("acme", activity).tasks[0])
    assert states[StepKey.AFTER] is StepState.DONE and states[StepKey.FINAL] is StepState.YOU
    assert service.advance_all() == 0  # the final confirmation is yours


def test_a_failing_or_running_automation_after(service, activity, copilot, stores, checks, pipeline_store, project_data_service, project):  # noqa: F811
    from models.domain.pipeline import PipelineRun, RunStatus
    plain = _automation(pipeline_store, "Stato", "git_status")
    plan = _created(service, activity)
    login = plan.tasks[0].task
    service.set_options("acme", activity, PlanOptions(after_automation=plain.id))
    service._run_after(_plan(stores, activity), service.path("acme", activity).tasks[0], plain.id)
    assert pipeline_store.list_pipeline_runs(plain.id)[0].input == f"api {login}"
    running = pipeline_store.save_pipeline_run(PipelineRun(pipeline_id=plain.id, status=RunStatus.RUNNING))
    stores.plans.save(_plan(stores, activity).model_copy(update={"automation_runs": {f"{login}|after": running.id}}))
    assert _states(service.path("acme", activity).tasks[0])[StepKey.AFTER] is StepState.RUNNING
    failed = pipeline_store.save_pipeline_run(PipelineRun(pipeline_id=plain.id, status=RunStatus.FAILED, error="rotta"))
    stores.plans.save(_plan(stores, activity).model_copy(update={"automation_runs": {f"{login}|after": failed.id}}))
    step = next(item for item in service.path("acme", activity).tasks[0].steps if item.key is StepKey.AFTER)
    assert step.state is StepState.FAILED and step.detail == "rotta"
    service.retry("acme", activity, login, StepKey.AFTER)
    assert _states(service.path("acme", activity).tasks[0])[StepKey.AFTER] is StepState.TODO
    service.skip("acme", activity, login, StepKey.AFTER)
    assert _states(service.path("acme", activity).tasks[0])[StepKey.AFTER] is StepState.SKIPPED

    pipeline_store.save_pipeline(plain.model_copy(update={"active": False}))
    service._run_after(_plan(stores, activity), service.path("acme", activity).tasks[1], plain.id)
    assert "disattivata" in _plan(stores, activity).errors[f"{plan.tasks[1].task}|after"]
    assert _states(service.path("acme", activity).tasks[1]).get(StepKey.AFTER) is None  # analysis: no step
    service._checks = None
    stores.plans.save(_plan(stores, activity).model_copy(update={"errors": {}, "skipped": []}))
    service._run_after(_plan(stores, activity), service.path("acme", activity).tasks[0], plain.id)
    assert "non sono disponibili" in _plan(stores, activity).errors[f"{login}|after"]
    stores.plans.save(_plan(stores, activity).model_copy(update={"errors": {}, "automation_runs": {f"{login}|after": 9999}}))
    task = project_data_service.agent_task("acme", login)
    project_data_service.save_agent_task("acme", login, task.model_copy(update={"status": TaskStatus.DONE}))
    assert _states(service.path("acme", activity).tasks[0])[StepKey.AFTER] is StepState.SKIPPED  # a done task never ran it


def test_the_round_approves_copilots_plan_by_itself_when_asked(service, activity, copilot, stores):
    plan = _created(service, activity)
    login = plan.tasks[0].task
    service.set_options("acme", activity, PlanOptions(prepare="none"))
    service.set_paused("acme", activity, False)
    service.advance_all()  # delegated: Copilot's plan waits for the ok
    session_id = copilot.list[0].id
    assert service.advance_all() == 0  # off by default

    service.set_options("acme", activity, PlanOptions(prepare="none", auto_approve=True))
    copilot.unanswered.add(session_id)
    assert service.advance_all() == 0  # Copilot has not answered yet
    copilot.unanswered.clear()
    assert service.advance_all() == 1 and copilot.approvals == [session_id]
    assert _plan(stores, activity).approved == [login]
    copilot.list = [item.model_copy(update={"status": CopilotSessionStatus.PLANNING}) for item in copilot.list]
    assert service.advance_all() == 0  # once per task: after an execution the chat is the user's


def test_once_every_task_is_done_the_summary_is_ready(service, activity, copilot, stores, project_data_service):
    plan = _created(service, activity)
    login, analysis = (item.task for item in plan.tasks)
    assert service.path("acme", activity).summary == ""
    for name in (login, analysis):
        task = project_data_service.agent_task("acme", name)
        project_data_service.save_agent_task("acme", name, task.model_copy(update={"status": TaskStatus.DONE}))
    copilot.list = [_session(4, login, CopilotSessionStatus.DONE, changed_files=["auth.py", "otp.py"])]
    stores.plans.save(_plan(stores, activity).model_copy(update={"skipped": [f"{login}|verify"]}))

    summary = service.path("acme", activity).summary
    assert summary.startswith("Task fatti: 2 di 2")
    assert "✓ Login (sviluppo; file cambiati: auth.py, otp.py; saltati: verifica)" in summary
    assert "✓ Analizza (analisi)" in summary and "Copilot 0,50 crediti AI" in summary and "Pianificatore" in summary
    project_data_service.delete_note("acme", analysis)
    assert f"✗ {analysis}: cancellato" in service.path("acme", activity).summary
    copilot.list = []
    assert "crediti AI" not in service.path("acme", activity).summary
