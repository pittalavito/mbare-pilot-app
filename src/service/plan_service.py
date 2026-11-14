"""«▶️ Lavora attività» (plan 12a): from an activity to its agent tasks, in order,
and the path of each one.

1. **Propose**: **one call** to the secretary's model with its ``plan_prompt``
   (``""`` = ``DEFAULT_PLAN_PROMPT``) and a **structured answer**
   (``PlanAnswer``), no tools, few tokens: the activity's title, description
   and items not done yet (numbered), the project's repositories, the task
   types and the 3 nearest pieces of the context index. Masked like «Elabora
   WIP»; the proposals come back in clear. A task on items that do not exist
   loses them; one without items is «new». Recorded as an agent run (origin
   ``plan``) and as the activity's plan, waiting for the user.
2. **Confirm** (no LLM): the chosen proposals, as corrected, in the given
   order become agent tasks «in refinement» with objective and criteria,
   linked to their items (a new one gets its item first) and to the activity.
3. **Path** (no LLM): for each task of the plan its steps, derived from the
   task's status and its latest Copilot session: confirmation of the task,
   preparation and delegation, Copilot's plan, execution, verification (or
   the answer, for the types that do not change the code), final
   confirmation. The steps waiting for the user are the control points.
4. **Advance** (plan 12b, the worker, no LLM of its own): a confirmed path not
   paused moves on by itself at the current task: once the task is confirmed
   it prepares the repositories (the plan's choice: a learned automation,
   «Prepara sviluppo» or nothing) and delegates with Copilot's defaults; failed
   tests go back to Copilot by themselves up to the project's ``auto_retries``.
   Everything else waits for the user (pause, retry, skip a step).
5. **12c**: the activity's automations before and after each development task
   (no LLM, the fields from the task), the automatic ok to Copilot's plan
   (switched on per activity) and, once no task is left, the summary composed
   by the code, to put in «Imparato»."""
import json
from time import perf_counter
from uuid import uuid4

from datapizza.tracing import ContextTracing

from core.error import AppError, ConflictError, NotFoundError, UpstreamError, ValidationError
from core.observability import LogPrefix, log_exception, observed
from domain.agent.tracing import Adapter as TracingAdapter
from domain.chat.chatbots_default import DEFAULT_PLAN_PROMPT
from domain.masking.preview import masked_text, unmask
from domain.project.data_paths import note_file_name
from models.domain.agent import AgentRunRecord, RunOrigin
from models.domain.chat import split_model_key
from models.domain.chatbot import Chatbot, ChatbotKind
from models.domain.copilot import CopilotMessageRole, CopilotSession, CopilotSessionStatus
from models.domain.dev import PREPARE_AUTOMATION, VERIFY_FAILED, VERIFY_OK, LearnedPreparation, PrepareTarget
from models.domain.masking import MaskCategory
from models.domain.note import Activity, AgentTask, ChecklistItem, TaskStatus, TaskType, TodoItem
from models.domain.pipeline import AutomationPurpose, RunStatus
from models.domain.plan import (
    RETRYABLE,
    SKIPPABLE,
    STEP_LABELS,
    ActivityPath,
    ActivityPlan,
    PathStep,
    PathTask,
    PlanAnswer,
    PlanChoice,
    PlanOptions,
    PlanProposal,
    PlanStatus,
    PlanTask,
    StepKey,
    StepState,
    step_id,
)
from service.chat_service import ChatService
from service.copilot_service import CopilotService
from service.dev_checks_service import DevChecksService
from service.git_service import GitService
from service.masking_service import MaskingService
from service.model_service import require_usable_model
from service.project_data_service import ProjectDataService
from service.rag_service import RagService
from service.store.catalog_store import CatalogStore
from service.store.chatbot_store import ChatbotStore
from service.store.pipeline_store import PipelineStore
from service.store.plan_store import PlanStore
from service.store.run_store import RunStore

PREPARE_NONE = "none"
PREPARE_DEV = "dev"
LEARNED = "learned:"
PREPARE_FAILED = "Preparazione non riuscita"
"""How CopilotService.start says the preparation failed (the delegation did not start)."""
CONTEXT_PIECES = 3
"""How many pieces of the context index the Pianificatore reads."""
_PIECE_CHARS = 500
TYPE_WORDS = {TaskType.DEVELOPMENT: "sviluppo", TaskType.ANALYSIS: "analisi", TaskType.CONFLUENCE: "Confluence", TaskType.JIRA: "Jira"}
_TYPES = "development (cambia il codice), analysis (analisi del codice), confluence (pagina Confluence), jira (issue Jira)"


class PlanService:

    def __init__(self, project_data: ProjectDataService, masking: MaskingService, chatbots: ChatbotStore, chat: ChatService,
                 catalog: CatalogStore, runs: RunStore, plans: PlanStore, git: GitService, rag: RagService | None = None,
                 copilot: CopilotService | None = None, pipelines: PipelineStore | None = None):
        self._data = project_data
        self._masking = masking
        self._chatbots = chatbots
        self._chat = chat
        self._catalog = catalog
        self._runs = runs
        self._plans = plans
        self._git = git
        self._rag = rag
        self._copilot = copilot
        self._pipelines = pipelines
        """The project's automations: which learned preparation, whether «Prepara sviluppo» is there."""
        self._checks: DevChecksService | None = None

    def use_checks(self, checks: "DevChecksService") -> None:
        """Runs the automations before and after each task (12c). Set after construction, like Copilot's."""
        self._checks = checks

    # --------------------------------------------------------------- propose
    @observed(LogPrefix.PLAN_SERVICE)
    def propose(self, project_name: str, activity_name: str) -> ActivityPlan:
        """The Pianificatore's proposals for the activity (a new plan: the old one is replaced)."""
        name = note_file_name(activity_name)
        activity = self._data.activity(project_name, name)
        open_items = {number: item.text for number, item in enumerate(activity.items, 1) if not item.done and not item.agent_task}
        repositories = [repository.path for repository in self._git.repositories(project_name)]
        for path in repositories:
            self._masking.register(project_name, MaskCategory.REPOSITORY, path)
        entries = self._masking.entries(project_name)
        masked = masked_text(model_input(activity, open_items, repositories, self._context(project_name, activity)), entries)
        secretary = self._secretary(project_name)
        require_usable_model(self._catalog, secretary.model)
        client = self._chat.get_client(secretary.model)

        answer, error = None, None
        start = perf_counter()
        with ContextTracing().trace(f"plan.{secretary.name}") as current_trace:
            try:
                response = client.structured_response(input=masked.text, output_cls=PlanAnswer,
                                                      system_prompt=secretary.plan_prompt or DEFAULT_PLAN_PROMPT)
                if not response.structured_data:
                    raise ValueError("nessuna risposta strutturata")
                data = response.structured_data[0]
                answer = PlanAnswer.model_validate(data.model_dump() if hasattr(data, "model_dump") else data)
            except Exception as exc:  # noqa: BLE001 - any failure of the call is recorded and reported
                log_exception(LogPrefix.PLAN_SERVICE, "Pianificatore fallito (%s · %s)", project_name, name)
                error = str(exc) or type(exc).__name__
            telemetry = TracingAdapter.to_run_telemetry(current_trace.get_spans(), self._catalog.price_list())
        latency_ms = round((perf_counter() - start) * 1000, 1)

        clear = lambda text: unmask(text, entries, masked.temporary).strip()  # noqa: E731
        proposals = to_proposals(answer, open_items, repositories, clear) if answer else []
        run_id = str(uuid4())
        self._runs.save(AgentRunRecord(
            run_id=run_id, project_name=project_name, origin=RunOrigin.PLAN, config_name=f"plan/{secretary.name}", role_name="plan",
            prompt_id=0, prompt_version=secretary.plan_prompt_version, model=split_model_key(secretary.model)[1], ok=error is None,
            error=error, latency_ms=latency_ms, input=unmask(masked.text, entries, masked.temporary),
            output=json.dumps([proposal.model_dump(mode="json") for proposal in proposals], ensure_ascii=False), telemetry=telemetry,
        ))
        if error is not None:
            raise UpstreamError(f"Il Pianificatore non ha risposto: {error}")
        return self._plans.save(ActivityPlan(project_name=project_name, activity=name, run_id=run_id, proposals=proposals,
                                             cost_eur=round(telemetry.total_tokens.cost_eur, 6)))

    def _context(self, project_name: str, activity: Activity) -> list[str]:
        """The nearest pieces of the context index, as lines; none without an index (best effort)."""
        if self._rag is None:
            return []
        question = f"{activity.title}\n{activity.description}".strip()
        try:
            hits = self._rag.search(project_name, question, limit=CONTEXT_PIECES)
        except AppError:
            return []
        return [f"[{hit.title}{' · ' + hit.section if hit.section else ''}] {' '.join(hit.text.split())[:_PIECE_CHARS]}" for hit in hits]

    def _secretary(self, project_name: str) -> Chatbot:
        secretary = next((bot for bot in self._chatbots.list_chatbots(project_name) if bot.kind is ChatbotKind.SECRETARY), None)
        if secretary is None:
            raise ValidationError("Nessun segretario nel progetto: il chatbot di default si crea all'avvio dell'API (se manca, guarda il log).")
        return secretary

    # --------------------------------------------------------------- confirm
    @observed(LogPrefix.PLAN_SERVICE)
    def confirm(self, project_name: str, activity_name: str, choices: list[PlanChoice]) -> ActivityPlan:
        """The chosen proposals become agent tasks «in refinement», in the order of ``choices``."""
        plan = self._open_plan(project_name, activity_name)
        if not choices:
            raise ValidationError("Scegli almeno un task, oppure scarta il piano.")
        proposals = {proposal.id: proposal for proposal in plan.proposals}
        unknown = [choice.id for choice in choices if choice.id not in proposals]
        if unknown:
            raise ValidationError(f"Proposte che il piano non ha: {', '.join(map(str, unknown))}.")
        activity = self._data.activity(project_name, plan.activity)
        tasks: list[PlanTask] = []
        for choice in choices:
            proposal = proposals[choice.id]
            items = self._items(project_name, plan.activity, proposal, choice.title)
            context = f"Nasce dall'attività «{activity.title}»." + (f"\n\n{activity.description.strip()}" if activity.description.strip() else "")
            task = self._data.create_agent_task(project_name, AgentTask(
                title=choice.title.strip(), status=TaskStatus.REFINEMENT, type=choice.type, objective=choice.objective.strip(), context=context,
                criteria=[ChecklistItem(text=text.strip()) for text in choice.criteria if text.strip()], references=activity.references))
            for number in items:
                self._data.link_item(project_name, plan.activity, number, task)
            self._data.link_agent_task(project_name, plan.activity, task)
            tasks.append(PlanTask(task=task, repository=choice.repository.strip()))
        return self._plans.save(plan.model_copy(update={"status": PlanStatus.CONFIRMED, "tasks": tasks}))

    def _items(self, project_name: str, activity_name: str, proposal: PlanProposal, title: str) -> list[int]:
        """The proposal's items still as they were (free, same text); a new task gets its item at the end of the todo list."""
        activity = self._data.activity(project_name, activity_name)
        if proposal.new:
            self._data.save_activity(project_name, activity_name, activity.model_copy(update={"items": [*activity.items, TodoItem(text=title.strip())]}))
            return [len(activity.items) + 1]
        return [number for number, text in zip(proposal.items, proposal.item_texts, strict=True)
                if 0 < number <= len(activity.items) and activity.items[number - 1].text == text and not activity.items[number - 1].agent_task]

    def dismiss(self, project_name: str, activity_name: str) -> ActivityPlan:
        """The proposals closed without creating anything."""
        plan = self._open_plan(project_name, activity_name)
        return self._plans.save(plan.model_copy(update={"status": PlanStatus.DISMISSED}))

    def _open_plan(self, project_name: str, activity_name: str) -> ActivityPlan:
        plan = self._plans.latest(project_name, note_file_name(activity_name))
        if plan is None:
            raise NotFoundError("L'attività non ha un piano: premi «▶️ Lavora attività».")
        if plan.status is not PlanStatus.PROPOSED:
            raise ConflictError("Il piano non aspetta più una scelta: ricarica.")
        return plan

    def waiting(self, project_name: str) -> list[ActivityPlan]:
        """The plans whose proposals wait for the user («📌 Oggi»)."""
        return [plan for plan in self._plans.latest_per_activity(project_name) if plan.status is PlanStatus.PROPOSED]

    # ------------------------------------------------------------------ path
    def path(self, project_name: str, activity_name: str) -> ActivityPath:
        """The activity's latest plan and, once confirmed, the steps of each task."""
        plan = self._plans.latest(project_name, note_file_name(activity_name))
        if plan is None or plan.status is not PlanStatus.CONFIRMED:
            return ActivityPath(plan=plan if plan and plan.status is PlanStatus.PROPOSED else None)
        tasks = self._tasks(plan)
        summary = self._summary(plan, tasks) if tasks and not any(item.current for item in tasks) else ""
        return ActivityPath(plan=plan, tasks=tasks, summary=summary)

    def _tasks(self, plan: ActivityPlan) -> list[PathTask]:
        tasks = dict(self._data.agent_tasks(plan.project_name))
        sessions = self._copilot.sessions(plan.project_name) if self._copilot else []
        result = [self._path_task(plan, planned, tasks.get(planned.task), next((item for item in sessions if item.task_note == planned.task), None))
                  for planned in plan.tasks]
        current = next((item for item in result if item.status not in (TaskStatus.DONE.value, "missing")), None)
        if current is not None:
            current.current = True
        return result

    def confirm_task(self, project_name: str, task_note: str) -> None:
        """«Conferma del task»: objective and criteria are fine, the task is «to do» (ready to delegate)."""
        name = note_file_name(task_note)
        task = self._data.agent_task(project_name, name)
        if task.status.is_refined:
            raise ConflictError("Il task è già confermato.")
        if not task.objective.strip():
            raise ValidationError("Il task non ha un obiettivo: scrivilo (o chiedi al Refiner) prima di confermarlo.")
        self._data.save_agent_task(project_name, name, task.model_copy(update={"status": TaskStatus.TODO}))

    def _path_task(self, plan: ActivityPlan, planned: PlanTask, task: AgentTask | None, session: CopilotSession | None) -> PathTask:
        if task is None:
            return PathTask(task=planned.task, title=planned.task, type=TaskType.DEVELOPMENT, status="missing", repository=planned.repository)
        return PathTask(task=planned.task, title=task.title, type=task.type, status=task.status.value, repository=planned.repository,
                        session_id=session.id if session else None, steps=self._steps(plan, planned.task, task, session))

    def _steps(self, plan: ActivityPlan, name: str, task: AgentTask, session: CopilotSession | None) -> list[PathStep]:
        done = task.status is TaskStatus.DONE
        error = lambda key: plan.errors.get(step_id(name, key), "")  # noqa: E731
        skipped = lambda key: step_id(name, key) in plan.skipped  # noqa: E731
        steps = [(StepKey.CONFIRM, StepState.DONE if task.status.is_refined else StepState.YOU, "")]
        if not task.type.plan_only and (before := self._automation_step(plan, name, StepKey.BEFORE, plan.before_automation, done)):
            steps.append(before)
        if not task.type.plan_only:
            if error(StepKey.PREPARE):
                prepare = (StepState.FAILED, error(StepKey.PREPARE))
            elif skipped(StepKey.PREPARE):
                prepare = (StepState.SKIPPED, "")
            else:
                prepare = (StepState.DONE if session or done else StepState.TODO, "")
            steps.append((StepKey.PREPARE, *prepare))
        if error(StepKey.DELEGATE):
            steps.append((StepKey.DELEGATE, StepState.FAILED, error(StepKey.DELEGATE)))
        else:
            steps.append((StepKey.DELEGATE, StepState.DONE if session or done else StepState.TODO, session.repository if session else ""))
        status = session.status if session else None
        if task.type.plan_only:
            answer = StepState.DONE if done else StepState.YOU if status is CopilotSessionStatus.PLANNING else (
                StepState.FAILED if status in (CopilotSessionStatus.FAILED, CopilotSessionStatus.CANCELLED) else StepState.TODO)
            steps.append((StepKey.ANSWER, answer, ""))
            return _path_steps(steps)
        if status is None:
            plan_state = StepState.DONE if done else StepState.TODO
        else:
            plan_state = StepState.YOU if status is CopilotSessionStatus.PLANNING else StepState.DONE
        steps.append((StepKey.COPILOT_PLAN, plan_state, ""))
        execution = {CopilotSessionStatus.QUEUED: StepState.RUNNING, CopilotSessionStatus.RUNNING: StepState.RUNNING,
                     CopilotSessionStatus.DONE: StepState.DONE, CopilotSessionStatus.FAILED: StepState.FAILED,
                     CopilotSessionStatus.CANCELLED: StepState.FAILED}.get(status, StepState.DONE if done else StepState.TODO) if status else (
            StepState.DONE if done else StepState.TODO)
        steps.append((StepKey.EXECUTION, execution, session.error or "" if session else ""))
        verify, detail = (StepState.SKIPPED, "") if skipped(StepKey.VERIFY) else self._verify(session, done)
        sent = plan.retries.get(name, 0)
        steps.append((StepKey.VERIFY, verify, ", ".join(part for part in (detail, f"rimandato a Copilot {sent} volte" if sent else "") if part)))
        if (after := self._automation_step(plan, name, StepKey.AFTER, plan.after_automation, done)):
            steps.append(after)
        final = StepState.DONE if done else StepState.YOU if task.status is TaskStatus.TO_VERIFY else StepState.TODO
        steps.append((StepKey.FINAL, final, ""))
        return _path_steps(steps)

    def _automation_step(self, plan: ActivityPlan, name: str, key: StepKey, automation: int | None,
                         done: bool) -> tuple[StepKey, StepState, str] | None:
        """A step of the automation before or after a task; None when the activity has none and none ran."""
        key_id = step_id(name, key)
        run_id = plan.automation_runs.get(key_id)
        if automation is None and run_id is None:
            return None
        if key_id in plan.skipped:
            return key, StepState.SKIPPED, ""
        if plan.errors.get(key_id):
            return key, StepState.FAILED, plan.errors[key_id]
        run = self._pipelines.get_pipeline_run(run_id) if run_id is not None and self._pipelines else None
        if run is None:
            return key, StepState.SKIPPED if done else StepState.TODO, ""
        if run.status is RunStatus.DONE:
            return key, StepState.DONE, ""
        if run.status is RunStatus.FAILED:
            return key, StepState.FAILED, run.error or "fallita"
        return key, StepState.RUNNING, ""

    def _verify(self, session: CopilotSession | None, done: bool) -> tuple[StepState, str]:
        """From the session's latest verification event: ok, failed, or skipped (no «Verifica sviluppo» ran)."""
        verification = self._verification(session)
        if verification is None:
            if session is None or session.status is not CopilotSessionStatus.DONE or self._copilot is None:
                return (StepState.DONE if done else StepState.TODO), ""
            return StepState.SKIPPED, ""
        return (StepState.DONE, "") if verification.startswith(VERIFY_OK) else (StepState.FAILED, "test falliti")

    def _verification(self, session: CopilotSession | None) -> str | None:
        """The latest verification event of a finished execution; None when there is none."""
        if session is None or session.status is not CopilotSessionStatus.DONE or self._copilot is None or session.id is None:
            return None
        events = [message.content for message in self._copilot.messages(session.id) if message.role is CopilotMessageRole.EVENT]
        return next((text for text in reversed(events) if text.startswith((VERIFY_OK, VERIFY_FAILED))), None)

    # ------------------------------------------------------------- controls
    def set_paused(self, project_name: str, activity_name: str, paused: bool) -> ActivityPlan:
        """Pause or resume the activity's path."""
        return self._plans.save(self._confirmed(project_name, activity_name).model_copy(update={"paused": paused}))

    def set_prepare(self, project_name: str, activity_name: str, prepare: str) -> ActivityPlan:
        """How the path prepares the repositories: ``""``, ``none``, ``dev`` or ``learned:<id>``."""
        if prepare not in ("", PREPARE_NONE, PREPARE_DEV) and not (prepare.startswith(LEARNED) and prepare[len(LEARNED):].isdigit()):
            raise ValidationError(f"Preparazione non valida: {prepare}")
        return self._plans.save(self._confirmed(project_name, activity_name).model_copy(update={"prepare": prepare}))

    def skip(self, project_name: str, activity_name: str, task: str, step: StepKey) -> ActivityPlan:
        """Skip a step of a task (preparation, verification): the path goes on without it."""
        plan = self._step_of(project_name, activity_name, task, step, SKIPPABLE, "saltare")
        key = step_id(task, step)
        errors = {item: text for item, text in plan.errors.items() if item != key}
        return self._plans.save(plan.model_copy(update={"skipped": [*dict.fromkeys([*plan.skipped, key])], "errors": errors}))

    def retry(self, project_name: str, activity_name: str, task: str, step: StepKey) -> ActivityPlan:
        """Run a failed step again: the preparation and the delegation at the path's next turn, the verification now."""
        plan = self._step_of(project_name, activity_name, task, step, RETRYABLE, "riprovare")
        if step is StepKey.VERIFY:
            session = next((item for item in self._copilot.sessions(project_name) if item.task_note == task), None) if self._copilot else None
            if session is None or session.id is None or self._copilot is None:
                raise ConflictError("Il task non ha un'esecuzione di Copilot da verificare.")
            self._copilot.verify_again(session.id)
            return plan
        key = step_id(task, step)
        return self._plans.save(plan.model_copy(update={"errors": {item: text for item, text in plan.errors.items() if item != key},
                                                         "automation_runs": {item: run for item, run in plan.automation_runs.items() if item != key}}))

    def set_options(self, project_name: str, activity_name: str, options: PlanOptions) -> ActivityPlan:
        """The automations before and after each task (of this project) and the automatic ok to Copilot's plan."""
        plan = self._confirmed(project_name, activity_name)
        for automation in (options.before_automation, options.after_automation):
            pipeline = self._pipelines.get_pipeline(automation) if automation is not None and self._pipelines else None
            if automation is not None and (pipeline is None or pipeline.project_name != project_name):
                raise ValidationError(f"Automation non trovata nel progetto: {automation}")
        return self._plans.save(plan.model_copy(update=options.model_dump()))

    def _confirmed(self, project_name: str, activity_name: str) -> ActivityPlan:
        plan = self._plans.latest(project_name, note_file_name(activity_name))
        if plan is None or plan.status is not PlanStatus.CONFIRMED:
            raise ConflictError("L'attività non ha un piano confermato.")
        return plan

    def _step_of(self, project_name: str, activity_name: str, task: str, step: StepKey, allowed: set[StepKey], what: str) -> ActivityPlan:
        plan = self._confirmed(project_name, activity_name)
        if not any(item.task == task for item in plan.tasks):
            raise NotFoundError(f"Il task {task} non è nel piano.")
        if step not in allowed:
            raise ValidationError(f"Non si può {what} il passo «{STEP_LABELS[step]}».")
        return plan

    # -------------------------------------------------------------- advance
    def advance_all(self) -> int:
        """The worker's turn: every running path one step on where it can. Returns how many steps it took."""
        moved = 0
        for plan in self._plans.running():
            try:
                moved += self.advance(plan)
            except Exception:  # noqa: BLE001 - one broken path never stops the others
                log_exception(LogPrefix.PLAN_SERVICE, "Percorso di %s · %s non avanzato", plan.project_name, plan.activity)
        return moved

    def advance(self, plan: ActivityPlan) -> int:
        """At the current task: delegate it (with its preparation) once confirmed, or send its failed tests
        back to Copilot while retries last. 1 when it did something; the rest waits for the user."""
        if plan.paused or plan.status is not PlanStatus.CONFIRMED or self._copilot is None:
            return 0
        current = next((item for item in self._tasks(plan) if item.current), None)
        if current is None:
            return 0
        states = {step.key: step.state for step in current.steps}
        if states.get(StepKey.CONFIRM) is not StepState.DONE:
            return 0
        if states.get(StepKey.BEFORE) is StepState.TODO and plan.before_automation is not None:
            self._run_automation(plan, current, StepKey.BEFORE, plan.before_automation)
            return 1
        if states.get(StepKey.BEFORE) in (StepState.FAILED, StepState.RUNNING):
            return 0
        if states.get(StepKey.DELEGATE) is StepState.TODO and states.get(StepKey.PREPARE) is not StepState.FAILED:
            self._delegate(plan, current)
            return 1
        if (states.get(StepKey.COPILOT_PLAN) is StepState.YOU and plan.auto_approve and current.task not in plan.approved
                and current.session_id is not None):
            try:
                self._copilot.approve(current.session_id)
            except ConflictError:  # Copilot has not answered yet: next turn
                return 0
            self._plans.save(plan.model_copy(update={"approved": [*plan.approved, current.task]}))
            return 1
        if (states.get(StepKey.AFTER) is StepState.TODO and plan.after_automation is not None
                and states.get(StepKey.VERIFY) in (StepState.DONE, StepState.SKIPPED) and states.get(StepKey.FINAL) is StepState.YOU):
            self._run_automation(plan, current, StepKey.AFTER, plan.after_automation)
            return 1
        if states.get(StepKey.VERIFY) is StepState.FAILED and states.get(StepKey.FINAL) is StepState.YOU and current.session_id is not None:
            sent = plan.retries.get(current.task, 0)
            if sent >= self._data.auto_retries(plan.project_name):
                return 0
            failed = self._verification(self._copilot.session(current.session_id)) or VERIFY_FAILED
            text = f"La verifica dopo le tue modifiche è fallita:\n\n{failed[len(VERIFY_FAILED):].strip()}\n\nSistema e riprova."
            self._copilot.send_back(current.session_id, text)
            self._plans.save(plan.model_copy(update={"retries": {**plan.retries, current.task: sent + 1}}))
            return 1
        return 0

    def _delegate(self, plan: ActivityPlan, current: PathTask) -> None:
        """Preparation (as the plan says) and delegation with Copilot's default prompt and model; a failure is the step's error."""
        assert self._copilot is not None
        targets: list[PrepareTarget] = []
        learned: LearnedPreparation | None = None
        how = PREPARE_NONE if current.type.plan_only or step_id(current.task, StepKey.PREPARE) in plan.skipped else self._prepare_choice(plan)
        if how != PREPARE_NONE:
            fields = self._task_fields(plan, current)
            if how == PREPARE_DEV:
                targets = [PrepareTarget(repository=current.repository, branch=fields["branch"], base=fields["base"])]
            else:
                pipeline = self._pipelines.get_pipeline(int(how[len(LEARNED):])) if self._pipelines else None
                learned = LearnedPreparation(automation_id=int(how[len(LEARNED):]),
                                             fields={name: fields.get(name, "") for name in (pipeline.fields if pipeline else [])})
        try:
            self._copilot.start(plan.project_name, current.task, current.repository, prepare=targets, learned=learned)
        except AppError as exc:
            key = StepKey.PREPARE if str(exc).startswith(PREPARE_FAILED) else StepKey.DELEGATE
            self._plans.save(plan.model_copy(update={"errors": {**plan.errors, step_id(current.task, key): str(exc)}}))

    def _task_fields(self, plan: ActivityPlan, current: PathTask) -> dict[str, str]:
        """The values an automation's fields get from a task: branch = feature/<task>, base = the repository's current branch."""
        return {"branch": f"feature/{current.task.removeprefix('agent-task-').removesuffix('.md')}",
                "base": self._git.branches(plan.project_name, current.repository).current or "",
                "task": current.task, "repository": current.repository}

    def _run_automation(self, plan: ActivityPlan, current: PathTask, key: StepKey, automation: int) -> None:
        """The automation before or after a task, now (no LLM): its fields from the task, else «<repository> <task>»."""
        key_id = step_id(current.task, key)
        try:
            if self._checks is None or self._pipelines is None:
                raise ValidationError("Le automation del percorso non sono disponibili in questo processo.")
            pipeline = self._pipelines.get_pipeline(automation)
            if pipeline is not None and pipeline.fields:
                fields = self._task_fields(plan, current)
                text = json.dumps({name: fields.get(name, "") for name in pipeline.fields})
            else:
                text = f"{current.repository or '.'} {current.task}"
            check = self._checks.run_automation(plan.project_name, automation, text)
        except AppError as exc:
            self._plans.save(plan.model_copy(update={"errors": {**plan.errors, key_id: str(exc)}}))
            return
        self._plans.save(plan.model_copy(update={"automation_runs": {**plan.automation_runs, key_id: check.run_id}}))

    def _summary(self, plan: ActivityPlan, tasks: list[PathTask]) -> str:
        """What the path did, composed by the code (12c): tasks, files changed, tests sent back, cost."""
        lines = [f"Fatto con «▶️ Lavora attività» ({len([item for item in tasks if item.status == TaskStatus.DONE.value])} di {len(tasks)} task):"]
        credits = 0.0
        sessions = self._copilot.sessions(plan.project_name) if self._copilot else []
        for item in tasks:
            if item.status == "missing":
                lines.append(f"- ✗ {item.task}: cancellato")
                continue
            details = [TYPE_WORDS.get(item.type, item.type.value)]
            mine = [session for session in sessions if session.task_note == item.task]
            files = sorted({path for session in mine for path in session.changed_files})
            if files:
                details.append(f"file cambiati: {', '.join(files[:10])}" + (" …" if len(files) > 10 else ""))
            if plan.retries.get(item.task):
                details.append(f"test rimandati a Copilot {plan.retries[item.task]} volte")
            skipped = [STEP_LABELS[step.key].lower() for step in item.steps if step.state is StepState.SKIPPED]
            if skipped:
                details.append(f"saltati: {', '.join(skipped)}")
            for session in mine:
                if session.id is not None and self._copilot is not None:
                    credits += sum(turn.usage.ai_credits for turn in self._copilot.session_turns(session.id))
            lines.append(f"- {'✓' if item.status == TaskStatus.DONE.value else '…'} {item.title} ({'; '.join(details)})")
        cost = [f"Pianificatore {plan.cost_eur:.4f} €".replace(".", ",")]
        if credits:
            cost.append(f"Copilot {credits:.2f} crediti AI".replace(".", ","))
        lines.append(f"Costo: {', '.join(cost)}.")
        return "\n".join(lines)

    def _prepare_choice(self, plan: ActivityPlan) -> str:
        """The plan's choice, or the default: the first learned preparation, else «Prepara sviluppo», else none."""
        if plan.prepare:
            return plan.prepare
        pipelines = self._pipelines.list_pipelines(plan.project_name) if self._pipelines else []
        learned = next((item for item in pipelines if item.purpose is AutomationPurpose.PREPARE and item.active and item.id is not None), None)
        if learned is not None:
            return f"{LEARNED}{learned.id}"
        return PREPARE_DEV if any(item.name == PREPARE_AUTOMATION and item.active for item in pipelines) else PREPARE_NONE


def _path_steps(steps: list[tuple[StepKey, StepState, str]]) -> list[PathStep]:
    return [PathStep(key=key, label=STEP_LABELS[key], state=state, detail=detail) for key, state, detail in steps]


def model_input(activity: Activity, items: dict[int, str], repositories: list[str], context: list[str]) -> str:
    """The text the Pianificatore gets, before masking."""
    lines = [f"Attività: {activity.title}"]
    if activity.description.strip():
        lines.append(activity.description.strip())
    lines.append("\nVoci da fare:")
    lines += [f"{number}. {text}" for number, text in items.items()] or ["(nessuna)"]
    lines.append("\nRepository: " + (", ".join(path or "(cartella del progetto)" for path in repositories) or "(nessuno)"))
    lines.append(f"Tipi di task: {_TYPES}")
    if context:
        lines.append("\nContesto del progetto:")
        lines += [f"- {piece}" for piece in context]
    return "\n".join(lines)


def to_proposals(answer: PlanAnswer, items: dict[int, str], repositories: list[str], clear) -> list[PlanProposal]:
    """The answer in clear; items not in the list are dropped (a task left without any is «new»),
    a repository not in the project is left empty, a task without a title is dropped."""
    proposals: list[PlanProposal] = []
    for raw in answer.tasks:
        title = clear(raw.title)
        if not title:
            continue
        numbers = [number for number in dict.fromkeys(raw.items) if number in items]
        repository = clear(raw.repository).strip("/\\")
        proposals.append(PlanProposal(
            id=len(proposals) + 1, title=title, type=raw.type, repository=repository if repository in repositories else "",
            items=numbers, item_texts=[items[number] for number in numbers], new=not numbers, reason=clear(raw.reason),
            objective=clear(raw.objective), criteria=[clear(text) for text in raw.criteria if text.strip()],
        ))
    return proposals
