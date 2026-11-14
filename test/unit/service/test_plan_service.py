"""Plan 12a, «▶️ Lavora attività»: the Pianificatore (one structured call, fake
model) proposes the tasks of an activity, confirming creates them in order
with objective and criteria, and the path derives each task's steps from its
status and its Copilot session."""
import shutil
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.container import Container
from core.error import ConflictError, NotFoundError, UpstreamError, ValidationError
from domain.chat.chatbots_default import DEFAULT_PLAN_PROMPT
from fakes import FakeStructuredClient
from models.domain.chatbot import Chatbot, ChatbotKind
from models.domain.copilot import CopilotMessage, CopilotMessageRole, CopilotSession, CopilotSessionStatus
from models.domain.dev import VERIFY_FAILED, VERIFY_OK
from models.domain.note import Activity, AgentTask, TaskStatus, TaskType, TodoItem
from models.domain.plan import PlanAnswer, PlanChoice, PlannedTask, PlanStatus, StepKey, StepState
from models.domain.rag import RagHit
from service.chat_service import ChatService
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
def service(project, project_data_service, masking_service, chatbot_store, catalog_store, run_store, stores, client, git_service, copilot,  # noqa: F811
            monkeypatch):
    chatbot_store.save_chatbot(Chatbot(project_name="acme", name="Segretario", kind=ChatbotKind.SECRETARY, system_prompt="x", model=MODEL))
    chat = ChatService()
    monkeypatch.setattr(chat, "get_client", lambda model: client)
    return PlanService(project_data_service, masking_service, chatbot_store, chat, catalog_store, run_store, stores.plans, git_service,
                       FakeRag(), copilot, stores.pipelines)  # type: ignore[arg-type]


@pytest.fixture
def activity(project_data_service):
    return project_data_service.create_activity("acme", Activity(title="Login sicuro", description="OTP per tutti.", items=[
        TodoItem(text="Capire il flusso"), TodoItem(text="Chiedere l'OTP"), TodoItem(text="Mandare la mail"), TodoItem(text="Fatta", done=True),
    ]))


def test_the_pianificatore_proposes_the_tasks_from_one_masked_call(service, client, activity, run_store):
    plan = service.propose("acme", activity)

    call = client.calls[0]
    assert call["system_prompt"] == DEFAULT_PLAN_PROMPT and call["output_cls"] is PlanAnswer
    assert "1. Capire il flusso" in call["input"] and "Fatta" not in call["input"] and "[Architettura · Login] Il login passa da auth." in call["input"]
    assert "api" not in call["input"].split("Repository:")[1].split("\n")[0]  # the repositories are masked
    assert [proposal.title for proposal in plan.proposals] == ["Aggiorna la libreria", "Login con OTP", "Analizza il flusso"]
    first, second, third = plan.proposals
    assert first.new and first.repository == "web" and first.criteria == ["build ok"]
    assert second.items == [2, 3] and second.item_texts == ["Chiedere l'OTP", "Mandare la mail"] and not second.new
    assert third.repository == "" and third.type is TaskType.ANALYSIS
    assert plan.status is PlanStatus.PROPOSED and plan.cost_eur >= 0
    assert run_store.get_trace(plan.run_id) is not None
    assert service.path("acme", activity).plan.id == plan.id  # waiting for a choice


def test_confirming_creates_the_tasks_in_order_linked_to_their_items(service, activity, project_data_service):
    service.propose("acme", activity)
    plan = service.confirm("acme", activity, [
        PlanChoice(id=2, title="Login con OTP", type=TaskType.DEVELOPMENT, repository="api", objective=" Il login chiede l'OTP. ",
                   criteria=["test verdi", ""]),
        PlanChoice(id=1, title="Aggiorna la libreria 2.0", type=TaskType.DEVELOPMENT, repository="web", objective="Alla 2.0."),
    ])
    assert plan.status is PlanStatus.CONFIRMED and [item.repository for item in plan.tasks] == ["api", "web"]
    login = project_data_service.agent_task("acme", plan.tasks[0].task)
    assert login.status is TaskStatus.REFINEMENT and login.objective == "Il login chiede l'OTP." and [c.text for c in login.criteria] == ["test verdi"]
    saved = project_data_service.activity("acme", activity)
    assert saved.items[1].agent_task == saved.items[2].agent_task == plan.tasks[0].task
    assert saved.items[4].text == "Aggiorna la libreria 2.0" and saved.items[4].agent_task == plan.tasks[1].task  # the new task's item
    assert set(saved.agent_tasks) >= {item.task for item in plan.tasks}
    with pytest.raises(ConflictError):
        service.confirm("acme", activity, [PlanChoice(id=1, title="x", type=TaskType.DEVELOPMENT)])


def test_choices_are_checked_and_a_plan_can_be_dismissed(service, activity, project_data_service, stores, copilot):
    with pytest.raises(NotFoundError):
        service.dismiss("acme", activity)
    service.propose("acme", activity)
    with pytest.raises(ValidationError, match="almeno un task"):
        service.confirm("acme", activity, [])
    with pytest.raises(ValidationError, match="non ha: 7"):
        service.confirm("acme", activity, [PlanChoice(id=7, title="x", type=TaskType.DEVELOPMENT)])
    today = TodayService(project_data_service, None, stores.plans).today("acme")
    assert [(item.kind.value, item.task) for item in today.waiting] == [("plan", activity)]
    assert service.waiting("acme")[0].activity == activity

    assert service.dismiss("acme", activity).status is PlanStatus.DISMISSED
    assert service.path("acme", activity).plan is None and service.waiting("acme") == []


def test_an_item_that_changed_meanwhile_is_not_linked(service, activity, project_data_service):
    service.propose("acme", activity)
    saved = project_data_service.activity("acme", activity)
    items = [*saved.items]
    items[1] = items[1].model_copy(update={"text": "Chiedere l'OTP via SMS"})
    project_data_service.save_activity("acme", activity, saved.model_copy(update={"items": items}))
    plan = service.confirm("acme", activity, [PlanChoice(id=2, title="Login", type=TaskType.DEVELOPMENT)])
    after = project_data_service.activity("acme", activity)
    assert after.items[1].agent_task is None and after.items[2].agent_task == plan.tasks[0].task


def test_a_failing_model_or_no_secretary_is_reported(service, client, activity, chatbot_store, run_store):
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
    for bot in chatbot_store.list_chatbots("acme"):
        chatbot_store.delete_chatbot(bot.id)
    with pytest.raises(ValidationError, match="Nessun segretario"):
        service.propose("acme", activity)


def _session(id_, task, status, **fields):
    return CopilotSession(id=id_, project_name="acme", task_note=task, repository="api", copilot_session_id="x", mcp_token="t", status=status, **fields)


def _states(path_task):
    return {step.key: step.state for step in path_task.steps}


def test_the_path_follows_each_task_through_its_steps(service, activity, project_data_service, copilot):
    service.propose("acme", activity)
    plan = service.confirm("acme", activity, [PlanChoice(id=2, title="Login", type=TaskType.DEVELOPMENT, repository="api", objective="OTP"),
                                              PlanChoice(id=3, title="Analizza", type=TaskType.ANALYSIS, objective="Capire")])
    login, analysis = (item.task for item in plan.tasks)

    path = service.path("acme", activity)
    assert path.tasks[0].current and not path.tasks[1].current
    assert _states(path.tasks[0])[StepKey.CONFIRM] is StepState.YOU and _states(path.tasks[0])[StepKey.DELEGATE] is StepState.TODO
    assert [step.key for step in path.tasks[1].steps] == [StepKey.CONFIRM, StepKey.DELEGATE, StepKey.ANSWER]

    service.confirm_task("acme", login)
    with pytest.raises(ConflictError):
        service.confirm_task("acme", login)
    copilot.list = [_session(4, login, CopilotSessionStatus.PLANNING)]
    states = _states(service.path("acme", activity).tasks[0])
    assert states[StepKey.CONFIRM] is StepState.DONE and states[StepKey.DELEGATE] is StepState.DONE
    assert states[StepKey.COPILOT_PLAN] is StepState.YOU and states[StepKey.EXECUTION] is StepState.TODO

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


def test_model_input_without_items_repositories_or_context():
    text = model_input(Activity(title="Vuota"), {}, [], [])
    assert "(nessuna)" in text and "Repository: (nessuno)" in text and "Contesto" not in text
    assert "(cartella del progetto)" in model_input(Activity(title="X"), {}, [""], [])


def test_the_api_proposes_confirms_and_shows_the_path(project, stores, monkeypatch, project_data_service):  # noqa: F811
    container = Container(stores=stores)
    monkeypatch.setattr(container.chat_service, "get_client", lambda model: FakeStructuredClient(ANSWER))
    activity = project_data_service.create_activity("acme", Activity(title="Login", items=[TodoItem(text="a"), TodoItem(text="b"), TodoItem(text="c")]))
    with TestClient(create_app(container)) as client:
        proposed = client.post(f"/projects/acme/activities/{activity}/plan").json()
        assert len(proposed["proposals"]) == 3
        assert client.get("/projects/acme/today").json()["waiting"][0]["kind"] == "plan"
        confirmed = client.post(f"/projects/acme/activities/{activity}/plan/confirm",
                                json={"choices": [{"id": 1, "title": "Libreria", "type": "development", "objective": ""}]}).json()
        task = confirmed["tasks"][0]["task"]
        path = client.get(f"/projects/acme/activities/{activity}/path").json()
        assert path["tasks"][0]["steps"][0] == {"key": "confirm", "label": "Conferma del task", "state": "you", "detail": ""}
        assert client.post(f"/projects/acme/agent-tasks/{task}/confirm").status_code == 400  # no objective
        project_data_service.save_agent_task("acme", task, AgentTask(title="Libreria", status=TaskStatus.REFINEMENT, objective="2.0"))
        assert client.post(f"/projects/acme/agent-tasks/{task}/confirm").status_code == 204
        assert client.post(f"/projects/acme/activities/{activity}/plan/dismiss").status_code == 409
        client.post(f"/projects/acme/activities/{activity}/plan")
        assert client.post(f"/projects/acme/activities/{activity}/plan/dismiss").json()["status"] == "dismissed"


# ------------------------------------------------------------------- 12b

def _confirmed(service, activity, *choices):
    service.propose("acme", activity)
    return service.confirm("acme", activity, list(choices) or [
        PlanChoice(id=2, title="Login", type=TaskType.DEVELOPMENT, repository="api", objective="OTP"),
        PlanChoice(id=3, title="Analizza", type=TaskType.ANALYSIS, objective="Capire")])


def _plan(stores, activity):
    return stores.plans.latest("acme", activity)


def test_the_path_delegates_by_itself_once_the_task_is_confirmed(service, activity, copilot, stores, pipeline_store, git_service):
    plan = _confirmed(service, activity)
    login = plan.tasks[0].task
    assert service.advance_all() == 0  # waits for «Conferma del task»
    service.confirm_task("acme", login)

    assert service.advance_all() == 1
    assert copilot.started[0]["task"] == login and copilot.started[0]["repository"] == "api"
    assert copilot.started[0]["prepare"] == [] and copilot.started[0]["learned"] is None  # no preparation in the project
    states = _states(service.path("acme", activity).tasks[0])
    assert states[StepKey.PREPARE] is StepState.DONE and states[StepKey.COPILOT_PLAN] is StepState.YOU
    assert service.advance_all() == 0  # waits for the ok to Copilot's plan


def test_the_preparation_follows_the_plans_choice(service, activity, copilot, stores, pipeline_store, project):  # noqa: F811
    from domain.pipeline.graph import linear_edges
    from models.domain.dev import PREPARE_AUTOMATION
    from models.domain.pipeline import AutomationPurpose, Pipeline, PipelineStep, StepKind
    step = PipelineStep(name="1. git_fetch", kind=StepKind.TOOL, tool_name="git_fetch", params={"repository": "api"})
    learned = pipeline_store.save_pipeline(Pipeline(project_name="acme", name="Prepara", steps=[step], edges=linear_edges([step]),
                                                    fields=["branch", "base", "extra"], purpose=AutomationPurpose.PREPARE))
    dev = PipelineStep(name="Pulito", kind=StepKind.FUNCTION, function_name="git_check_clean")
    pipeline_store.save_pipeline(Pipeline(project_name="acme", name=PREPARE_AUTOMATION, steps=[dev], edges=linear_edges([dev])))
    plan = _confirmed(service, activity)
    login = plan.tasks[0].task
    service.confirm_task("acme", login)

    service.advance_all()  # default: the learned automation, its fields from the task
    started = copilot.started[0]["learned"]
    assert started.automation_id == learned.id
    assert started.fields["branch"] == f"feature/{login.removeprefix('agent-task-').removesuffix('.md')}" and started.fields["extra"] == ""
    assert started.fields["base"]  # the repository's current branch

    copilot.list = []
    service.set_prepare("acme", activity, "dev")
    service.advance_all()
    assert copilot.started[1]["prepare"][0].repository == "api" and copilot.started[1]["learned"] is None
    copilot.list = []
    service.set_prepare("acme", activity, "none")
    service.advance_all()
    assert copilot.started[2]["prepare"] == []
    with pytest.raises(ValidationError):
        service.set_prepare("acme", activity, "altro")
    copilot.list = []
    service.set_prepare("acme", activity, "")
    pipeline_store.save_pipeline(learned.model_copy(update={"active": False}))
    service.advance_all()
    assert copilot.started[3]["prepare"][0].branch.startswith("feature/")  # no learned one: «Prepara sviluppo»


def test_a_failed_preparation_stops_until_retried_or_skipped(service, activity, copilot, stores):
    plan = _confirmed(service, activity)
    login = plan.tasks[0].task
    service.confirm_task("acme", login)
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
        service.skip("acme", activity, login, StepKey.CONFIRM)
    with pytest.raises(ValidationError, match="Non si può riprovare"):
        service.retry("acme", activity, login, StepKey.FINAL)
    with pytest.raises(NotFoundError):
        service.skip("acme", activity, "agent-task-altro.md", StepKey.PREPARE)


def test_failed_tests_go_back_to_copilot_as_many_times_as_the_project_says(service, activity, copilot, stores, project_data_service):
    plan = _confirmed(service, activity)
    login = plan.tasks[0].task
    task = project_data_service.agent_task("acme", login)
    project_data_service.save_agent_task("acme", login, task.model_copy(update={"status": TaskStatus.TO_VERIFY}))
    copilot.list = [_session(4, login, CopilotSessionStatus.DONE)]
    copilot.events[4] = [f"{VERIFY_FAILED}\n\nFAILED test_login"]

    assert service.advance_all() == 1
    assert copilot.sent_back[0][0] == 4 and "FAILED test_login" in copilot.sent_back[0][1]
    copilot.list = [_session(4, login, CopilotSessionStatus.DONE)]
    path_task = service.path("acme", activity).tasks[0]
    assert "rimandato a Copilot 1 volte" in next(step for step in path_task.steps if step.key is StepKey.VERIFY).detail
    assert service.advance_all() == 0  # 1 retry by default: now it is the user's turn

    project_data_service.save_auto_retries("acme", 2)
    assert service.advance_all() == 1
    copilot.list = [_session(4, login, CopilotSessionStatus.DONE)]
    service.retry("acme", activity, login, StepKey.VERIFY)
    assert copilot.verified == [4]
    service.skip("acme", activity, login, StepKey.VERIFY)
    assert _states(service.path("acme", activity).tasks[0])[StepKey.VERIFY] is StepState.SKIPPED


def test_a_paused_path_waits_and_controls_need_a_confirmed_plan(service, activity, copilot, stores):
    with pytest.raises(ConflictError):
        service.set_paused("acme", activity, True)
    plan = _confirmed(service, activity)
    service.confirm_task("acme", plan.tasks[0].task)
    assert service.set_paused("acme", activity, True).paused
    assert service.advance_all() == 0 and stores.plans.running() == []
    assert service.advance(_plan(stores, activity)) == 0
    service.set_paused("acme", activity, False)
    assert service.advance_all() == 1
    with pytest.raises(ConflictError, match="da verificare"):
        copilot.list = []
        service.retry("acme", activity, plan.tasks[0].task, StepKey.VERIFY)


def test_one_broken_path_does_not_stop_the_others(service, activity, copilot, monkeypatch):
    plan = _confirmed(service, activity)
    service.confirm_task("acme", plan.tasks[0].task)
    monkeypatch.setattr(service, "advance", lambda plan: (_ for _ in ()).throw(RuntimeError("rotto")))
    assert service.advance_all() == 0


def test_without_copilot_or_with_every_task_done_nothing_moves(service, activity, copilot, project_data_service, stores):
    plan = _confirmed(service, activity, PlanChoice(id=2, title="Login", type=TaskType.DEVELOPMENT, objective="OTP"))
    task = project_data_service.agent_task("acme", plan.tasks[0].task)
    project_data_service.save_agent_task("acme", plan.tasks[0].task, task.model_copy(update={"status": TaskStatus.DONE}))
    assert service.advance_all() == 0
    service._copilot = None
    assert service.advance(_plan(stores, activity)) == 0


def test_the_api_pauses_chooses_skips_retries_and_saves_the_retries(project, stores, monkeypatch, project_data_service):  # noqa: F811
    container = Container(stores=stores)
    monkeypatch.setattr(container.chat_service, "get_client", lambda model: FakeStructuredClient(ANSWER))
    activity = project_data_service.create_activity("acme", Activity(title="Login", items=[TodoItem(text="a"), TodoItem(text="b"), TodoItem(text="c")]))
    with TestClient(create_app(container)) as client:
        assert client.post(f"/projects/acme/activities/{activity}/plan/pause", json={"paused": True}).status_code == 409
        client.post(f"/projects/acme/activities/{activity}/plan")
        task = client.post(f"/projects/acme/activities/{activity}/plan/confirm",
                           json={"choices": [{"id": 2, "title": "Login", "type": "development", "objective": "o"}]}).json()["tasks"][0]["task"]
        base = f"/projects/acme/activities/{activity}/plan"
        assert client.post(f"{base}/pause", json={"paused": True}).json()["paused"] is True
        assert client.post(f"{base}/prepare", json={"prepare": "dev"}).json()["prepare"] == "dev"
        assert client.post(f"{base}/prepare", json={"prepare": "x"}).status_code == 400
        assert client.post(f"{base}/skip", json={"task": task, "step": "prepare"}).json()["skipped"] == [f"{task}|prepare"]
        assert client.post(f"{base}/retry", json={"task": task, "step": "delegate"}).status_code == 200
        assert client.post(f"{base}/skip", json={"task": task, "step": "nope"}).status_code == 422
        assert client.put("/projects/acme/dev-settings", json={"auto_retries": 3}).json()["auto_retries"] == 3
        assert client.put("/projects/acme/dev-settings", json={"auto_retries": 4}).status_code == 422
        assert client.put("/projects/acme/dev-settings", json={}).json()["auto_retries"] == 3
        assert client.post(f"{base}/options", json={"auto_approve": True}).json()["auto_approve"] is True
        assert client.post(f"{base}/options", json={"before_automation": 999}).status_code == 400
        assert client.get(f"/projects/acme/activities/{activity}/path").json()["summary"] == ""


# ------------------------------------------------------------------- 12c

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
    step = PipelineStep(name=function, kind=StepKind.FUNCTION, function_name=function, params=params or {}, input_template="api")
    return pipeline_store.save_pipeline(Pipeline(project_name="acme", name=name, steps=[step], edges=linear_edges([step]), fields=list(fields)))


def test_the_automations_before_and_after_each_task_run_by_themselves(service, activity, copilot, stores, checks, pipeline_store,
                                                                      project_data_service, project):  # noqa: F811
    from models.domain.plan import PlanOptions
    before = _automation(pipeline_store, "Stato", "git_status")
    after = _automation(pipeline_store, "Log", "git_log", fields=["branch"])
    plan = _confirmed(service, activity)
    login = plan.tasks[0].task
    with pytest.raises(ValidationError, match="non trovata"):
        service.set_options("acme", activity, PlanOptions(before_automation=999))
    service.set_options("acme", activity, PlanOptions(before_automation=before.id, after_automation=after.id))
    service.set_prepare("acme", activity, "none")
    assert [step.key for step in service.path("acme", activity).tasks[0].steps][:2] == [StepKey.CONFIRM, StepKey.BEFORE]
    assert StepKey.BEFORE not in _states(service.path("acme", activity).tasks[1])  # not for analysis tasks
    service.confirm_task("acme", login)

    assert service.advance_all() == 1  # the automation before
    assert _states(service.path("acme", activity).tasks[0])[StepKey.BEFORE] is StepState.DONE
    run = pipeline_store.list_pipeline_runs(before.id)[0]
    assert run.input == f"api {login}"
    assert service.advance_all() == 1 and copilot.started  # then the delegation

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


def test_a_failing_automation_stops_the_path_until_retried_or_skipped(service, activity, copilot, stores, checks, pipeline_store,
                                                                      project_data_service, project):  # noqa: F811
    from models.domain.plan import PlanOptions
    failing = _automation(pipeline_store, "Pulito", "git_check_clean")
    (project / "api" / "README.md").write_text("cambiato", encoding="utf-8")
    plan = _confirmed(service, activity)
    login = plan.tasks[0].task
    service.set_options("acme", activity, PlanOptions(before_automation=failing.id))
    service.confirm_task("acme", login)

    service.advance_all()
    step = next(item for item in service.path("acme", activity).tasks[0].steps if item.key is StepKey.BEFORE)
    assert step.state is StepState.FAILED and step.detail
    assert service.advance_all() == 0 and not copilot.started
    service.retry("acme", activity, login, StepKey.BEFORE)
    assert _states(service.path("acme", activity).tasks[0])[StepKey.BEFORE] is StepState.TODO
    service.skip("acme", activity, login, StepKey.BEFORE)
    assert service.advance_all() == 1 and copilot.started

    pipeline_store.save_pipeline(failing.model_copy(update={"active": False}))
    service.set_options("acme", activity, PlanOptions(before_automation=failing.id))
    plan2 = _plan(stores, activity)
    service._run_automation(plan2, service.path("acme", activity).tasks[1], StepKey.BEFORE, failing.id)
    assert "disattivata" in _plan(stores, activity).errors[f"{plan.tasks[1].task}|before"]
    service._checks = None
    service._run_automation(_plan(stores, activity), service.path("acme", activity).tasks[0], StepKey.AFTER, failing.id)
    assert "non sono disponibili" in _plan(stores, activity).errors[f"{login}|after"]


def test_running_and_unran_automation_steps(service, activity, copilot, stores, checks, pipeline_store, project_data_service):
    from models.domain.pipeline import PipelineRun, RunStatus
    from models.domain.plan import PlanOptions
    automation = _automation(pipeline_store, "Stato", "git_status")
    plan = _confirmed(service, activity)
    login = plan.tasks[0].task
    service.set_options("acme", activity, PlanOptions(before_automation=automation.id))
    running = pipeline_store.save_pipeline_run(PipelineRun(pipeline_id=automation.id, status=RunStatus.RUNNING))
    stores.plans.save(_plan(stores, activity).model_copy(update={"automation_runs": {f"{login}|before": running.id}}))
    assert _states(service.path("acme", activity).tasks[0])[StepKey.BEFORE] is StepState.RUNNING
    service.confirm_task("acme", login)
    assert service.advance_all() == 0  # waits for it
    failed = pipeline_store.save_pipeline_run(PipelineRun(pipeline_id=automation.id, status=RunStatus.FAILED, error="rotta"))
    stores.plans.save(_plan(stores, activity).model_copy(update={"automation_runs": {f"{login}|before": failed.id}}))
    step = next(item for item in service.path("acme", activity).tasks[0].steps if item.key is StepKey.BEFORE)
    assert step.state is StepState.FAILED and step.detail == "rotta"
    stores.plans.save(_plan(stores, activity).model_copy(update={"automation_runs": {f"{login}|before": 9999}}))
    task = project_data_service.agent_task("acme", login)
    project_data_service.save_agent_task("acme", login, task.model_copy(update={"status": TaskStatus.DONE}))
    assert _states(service.path("acme", activity).tasks[0])[StepKey.BEFORE] is StepState.SKIPPED  # a done task never ran it


def test_the_path_approves_copilots_plan_by_itself_when_asked(service, activity, copilot, stores):
    from models.domain.plan import PlanOptions
    plan = _confirmed(service, activity)
    login = plan.tasks[0].task
    service.set_prepare("acme", activity, "none")
    service.confirm_task("acme", login)
    service.advance_all()  # delegated: Copilot's plan waits for the ok
    session_id = copilot.list[0].id
    assert service.advance_all() == 0  # off by default

    service.set_options("acme", activity, PlanOptions(auto_approve=True))
    copilot.unanswered.add(session_id)
    assert service.advance_all() == 0  # Copilot has not answered yet
    copilot.unanswered.clear()
    assert service.advance_all() == 1 and copilot.approvals == [session_id]
    assert _plan(stores, activity).approved == [login]
    copilot.list = [item.model_copy(update={"status": CopilotSessionStatus.PLANNING}) for item in copilot.list]
    assert service.advance_all() == 0  # once per task: after an execution the chat is the user's


def test_once_every_task_is_done_the_summary_is_ready_for_imparato(service, activity, copilot, stores, project_data_service):
    plan = _confirmed(service, activity)
    login, analysis = (item.task for item in plan.tasks)
    assert service.path("acme", activity).summary == ""
    for name in (login, analysis):
        task = project_data_service.agent_task("acme", name)
        project_data_service.save_agent_task("acme", name, task.model_copy(update={"status": TaskStatus.DONE}))
    copilot.list = [_session(4, login, CopilotSessionStatus.DONE, changed_files=["auth.py", "otp.py"])]
    stores.plans.save(_plan(stores, activity).model_copy(update={"retries": {login: 1}, "skipped": [f"{login}|verify"]}))

    summary = service.path("acme", activity).summary
    assert summary.startswith("Fatto con «▶️ Lavora attività» (2 di 2 task):")
    assert "✓ Login (sviluppo; file cambiati: auth.py, otp.py; test rimandati a Copilot 1 volte; saltati: verifica)" in summary
    assert "✓ Analizza (analisi)" in summary and "Copilot 0,50 crediti AI" in summary and "Pianificatore" in summary
    project_data_service.delete_note("acme", analysis)
    assert f"✗ {analysis}: cancellato" in service.path("acme", activity).summary
    copilot.list = []
    assert "crediti AI" not in service.path("acme", activity).summary
