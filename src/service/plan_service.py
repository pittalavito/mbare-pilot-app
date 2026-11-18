"""The plan of an activity and its round (plan 18): steps «Pianifica» and «Lavora».

1. **Propose** («✨ Proponi i task»): **one call** to the agent ``pianificatore``
   of global-agent.yml with a **structured answer** (``PlanAnswer``), no tools,
   few tokens: the activity's title, description and items not done and
   without a task (numbered), the titles of its references, the project's
   repositories, the task types and the 3 nearest pieces of the context index.
   Masked like «Elabora WIP»; the proposals come back in clear. A proposal on
   items that do not exist loses them; one without items is «new». The
   activity has **one plan**: the proposals wait in it next to the tasks
   already created (asked again, «Proponi altri task», they are for the
   items still uncovered).
2. **Create** (no LLM): the chosen proposals, as corrected, and the tasks
   written by hand, in the given order, become agent tasks **«to do»** with
   objective and criteria, linked to their items (a new one gets its item
   first) and to the activity, appended to the plan's tasks. The activity
   goes «in progress».
3. **Path** (no LLM): for each task its steps, derived from the task's status
   and its latest Copilot session: preparation and delegation, Copilot's plan,
   execution, verification and the automation after it (developments), or
   Copilot's answer (the types that do not change the code), final
   confirmation. The steps waiting for the user are the control points.
4. **Round** (the worker, no LLM of its own): started with «▶️ Avvia», stopped
   with «⏸ Pausa». At the current task (a task moved back to refinement waits)
   it prepares the repositories as the activity says (``none``, ``dev`` =
   «Prepara sviluppo», ``automation:<id>``) and delegates with Copilot's
   defaults; the fields of the preparation and of the automation after the
   verification come from the activity's template (``{task}``, ``{note}``,
   ``{repository}``, ``{base}``), resolved for each task, or from the task's own
   fields (plan 19); a task without a repository is not prepared (unless the
   project folder is a repository); it gives the ok to Copilot's plan only with ``auto_approve``; it
   runs the automation after the verification. Failed tests wait for the user
   (send back, retry, skip): nothing goes back to Copilot by itself.
5. Once no task is left, the **summary** composed by the code (step «Chiudi»)."""
import json

from core.error import AppError, ConflictError, NotFoundError, UpstreamError, ValidationError
from core.observability import LogPrefix, log_exception, observed
from domain.agent.outputs import PLAN, PLAN_AGENT
from domain.masking.preview import masked_text, unmask
from domain.project.data_paths import note_file_name
from models.domain.agent import RunOrigin
from models.domain.copilot import CopilotMessageRole, CopilotSession, CopilotSessionStatus
from models.domain.dev import PREPARE_AUTOMATION, VERIFY_FAILED, VERIFY_OK, LearnedPreparation, PrepareTarget
from models.domain.masking import MaskCategory
from models.domain.note import Activity, ActivityStatus, AgentTask, ChecklistItem, TaskStatus, TaskType, TodoItem
from models.domain.pipeline import RunStatus
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
    PlanTask,
    StepKey,
    StepState,
    TaskFields,
    step_id,
)
from service.copilot_service import CopilotService
from service.dev_checks_service import DevChecksService
from service.git_service import GitService
from service.masking_service import MaskingService
from service.project_data_service import ProjectDataService
from service.rag_service import RagService
from service.store.pipeline_store import PipelineStore
from service.store.plan_store import PlanStore
from service.structured_agent_service import StructuredAgentService

PREPARE_NONE = "none"
PREPARE_DEV = "dev"
AUTOMATION = "automation:"
DEV_FIELDS = ["branch", "base"]
"""The fields of «Prepara sviluppo»."""
DEFAULT_FIELDS = {"branch": "feature/{task}", "base": "{base}", "repository": "{repository}", "task": "{note}"}
"""A field's value when the template does not say; any other field starts empty."""
NO_REPOSITORY = "nessun repository"
PREPARE_FAILED = "Preparazione non riuscita"
"""How CopilotService.start says the preparation failed (the delegation did not start)."""
CONTEXT_PIECES = 3
"""How many pieces of the context index the Pianificatore reads."""
_PIECE_CHARS = 500
TYPE_WORDS = {TaskType.DEVELOPMENT: "sviluppo", TaskType.ANALYSIS: "analisi", TaskType.CONFLUENCE: "Confluence", TaskType.JIRA: "Jira"}
_TYPES = "development (cambia il codice), analysis (analisi del codice), confluence (pagina Confluence), jira (issue Jira)"


class PlanService:

    def __init__(self, project_data: ProjectDataService, masking: MaskingService, agents: StructuredAgentService,
                 plans: PlanStore, git: GitService, rag: RagService | None = None,
                 copilot: CopilotService | None = None, pipelines: PipelineStore | None = None):
        self._data = project_data
        self._masking = masking
        self._agents = agents
        self._plans = plans
        self._git = git
        self._rag = rag
        self._copilot = copilot
        self._pipelines = pipelines
        """The project's automations: the preparation and the automation after the verification."""
        self._checks: DevChecksService | None = None

    def use_checks(self, checks: "DevChecksService") -> None:
        """Runs the automation after each verification. Set after construction, like Copilot's."""
        self._checks = checks

    def plan(self, project_name: str, activity_name: str) -> ActivityPlan:
        """The activity's plan, a new empty one (not saved) when it has none yet."""
        name = note_file_name(activity_name)
        return self._plans.latest(project_name, name) or ActivityPlan(project_name=project_name, activity=name)

    # --------------------------------------------------------------- propose
    @observed(LogPrefix.PLAN_SERVICE)
    def propose(self, project_name: str, activity_name: str) -> ActivityPlan:
        """The Pianificatore's proposals for the items still without a task; the tasks already created stay."""
        plan = self.plan(project_name, activity_name)
        activity = self._data.activity(project_name, plan.activity)
        open_items = {number: item.text for number, item in enumerate(activity.items, 1) if not item.done and not item.agent_task}
        repositories = [repository.path for repository in self._git.repositories(project_name)]
        for path in repositories:
            self._masking.register(project_name, MaskCategory.REPOSITORY, path)
        agent = self._agents.agent(PLAN_AGENT, PLAN)
        entries = self._masking.entries(project_name)
        references = self._reference_titles(project_name, activity)
        masked = masked_text(model_input(activity, open_items, repositories, self._context(project_name, activity), references), entries)
        call = self._agents.call(agent, masked.text)

        clear = lambda text: unmask(text, entries, masked.temporary).strip()  # noqa: E731
        answer = call.answer if isinstance(call.answer, PlanAnswer) else None
        proposals = to_proposals(answer, open_items, repositories, clear) if answer else []
        run_id = self._agents.save(call, project_name=project_name, origin=RunOrigin.PLAN, input=unmask(masked.text, entries, masked.temporary),
                                   output=json.dumps([proposal.model_dump(mode="json") for proposal in proposals], ensure_ascii=False))
        if call.error is not None:
            raise UpstreamError(f"Il Pianificatore non ha risposto: {call.error}")
        return self._plans.save(plan.model_copy(update={
            "run_id": run_id, "proposals": proposals, "cost_eur": round(plan.cost_eur + call.telemetry.total_tokens.cost_eur, 6)}))

    def _reference_titles(self, project_name: str, activity: Activity) -> list[str]:
        """The titles of the activity's references; one that is gone is left out."""
        titles = []
        for name in activity.references:
            try:
                titles.append(self._data.reference(project_name, name)[1].title)
            except AppError:
                continue
        return titles

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

    # ---------------------------------------------------------------- create
    @observed(LogPrefix.PLAN_SERVICE)
    def confirm(self, project_name: str, activity_name: str, choices: list[PlanChoice]) -> ActivityPlan:
        """The chosen proposals and the tasks written by hand become agent tasks «to do», in the order of ``choices``."""
        plan = self.plan(project_name, activity_name)
        if not choices:
            raise ValidationError("Scegli almeno un task.")
        proposals = {proposal.id: proposal for proposal in plan.proposals}
        unknown = [str(choice.id) for choice in choices if choice.id is not None and choice.id not in proposals]
        if unknown:
            raise ConflictError(f"Proposte che il piano non ha più: {', '.join(unknown)}. Ricarica.")
        activity = self._data.activity(project_name, plan.activity)
        tasks: list[PlanTask] = []
        for choice in choices:
            items = self._items(project_name, plan.activity, proposals.get(choice.id) if choice.id is not None else None, choice)
            context = f"Nasce dall'attività «{activity.title}»." + (f"\n\n{activity.description.strip()}" if activity.description.strip() else "")
            task = self._data.create_agent_task(project_name, AgentTask(
                title=choice.title.strip(), status=TaskStatus.TODO, type=choice.type, objective=choice.objective.strip(), context=context,
                criteria=[ChecklistItem(text=text.strip()) for text in choice.criteria if text.strip()], references=activity.references))
            for number in items:
                self._data.link_item(project_name, plan.activity, number, task)
            self._data.link_agent_task(project_name, plan.activity, task)
            tasks.append(PlanTask(task=task, repository=choice.repository.strip()))
        current = self._data.activity(project_name, plan.activity)
        if current.status is ActivityStatus.TODO:
            self._data.save_activity(project_name, plan.activity, current.model_copy(update={"status": ActivityStatus.IN_PROGRESS}))
        return self._plans.save(plan.model_copy(update={"proposals": [], "tasks": [*plan.tasks, *tasks]}))

    def _items(self, project_name: str, activity_name: str, proposal: PlanProposal | None, choice: PlanChoice) -> list[int]:
        """The items still free and as they were: the proposal's (a new one gets its item at the end of the
        todo list), or the ones a task written by hand names."""
        activity = self._data.activity(project_name, activity_name)
        free = lambda number: 0 < number <= len(activity.items) and not activity.items[number - 1].agent_task  # noqa: E731
        if proposal is None:
            return [number for number in dict.fromkeys(choice.items) if free(number)]
        if proposal.new:
            self._data.save_activity(project_name, activity_name, activity.model_copy(update={"items": [*activity.items, TodoItem(text=choice.title.strip())]}))
            return [len(activity.items) + 1]
        return [number for number, text in zip(proposal.items, proposal.item_texts, strict=True)
                if free(number) and activity.items[number - 1].text == text]

    def dismiss(self, project_name: str, activity_name: str) -> ActivityPlan:
        """The proposals closed without creating anything; the tasks stay."""
        plan = self._plans.latest(project_name, note_file_name(activity_name))
        if plan is None:
            raise NotFoundError("L'attività non ha un piano.")
        return self._plans.save(plan.model_copy(update={"proposals": []}))

    def waiting(self, project_name: str) -> list[ActivityPlan]:
        """The plans whose proposals wait for the user («📌 Oggi»)."""
        return [plan for plan in self._plans.latest_per_activity(project_name) if plan.proposals]

    # ------------------------------------------------------------------ path
    def path(self, project_name: str, activity_name: str) -> ActivityPath:
        """The activity's plan (None when it has none) with the steps of each task; the summary once none is left."""
        plan = self._plans.latest(project_name, note_file_name(activity_name))
        if plan is None:
            return ActivityPath()
        tasks = self._tasks(plan)
        summary = self._summary(plan, tasks) if tasks and not any(item.current for item in tasks) else ""
        return ActivityPath(plan=plan, tasks=tasks, summary=summary)

    def _tasks(self, plan: ActivityPlan) -> list[PathTask]:
        tasks = dict(self._data.agent_tasks(plan.project_name))
        sessions = self._copilot.sessions(plan.project_name) if self._copilot else []
        root = self._root_is_repository(plan.project_name)
        result = [self._path_task(plan, planned, tasks.get(planned.task), next((item for item in sessions if item.task_note == planned.task), None), root)
                  for planned in plan.tasks]
        current = next((item for item in result if item.status not in (TaskStatus.DONE.value, "missing")), None)
        if current is not None:
            current.current = True
        return result

    def _root_is_repository(self, project_name: str) -> bool:
        """The project folder is itself a git repository: a task without a repository is prepared there."""
        try:
            return any(repository.path == "" for repository in self._git.repositories(project_name))
        except AppError:
            return False

    def _path_task(self, plan: ActivityPlan, planned: PlanTask, task: AgentTask | None, session: CopilotSession | None,
                   root: bool = False) -> PathTask:
        if task is None:
            return PathTask(task=planned.task, title=planned.task, type=TaskType.DEVELOPMENT, status="missing", repository=planned.repository)
        return PathTask(task=planned.task, title=task.title, type=task.type, status=task.status.value, repository=planned.repository,
                        session_id=session.id if session else None, steps=self._steps(plan, planned, task, session, root))

    def _steps(self, plan: ActivityPlan, planned: PlanTask, task: AgentTask, session: CopilotSession | None, root: bool) -> list[PathStep]:
        name = planned.task
        done = task.status is TaskStatus.DONE
        error = lambda key: plan.errors.get(step_id(name, key), "")  # noqa: E731
        skipped = lambda key: step_id(name, key) in plan.skipped  # noqa: E731
        steps: list[tuple[StepKey, StepState, str]] = []
        if not task.type.plan_only and (plan.prepare != PREPARE_NONE or error(StepKey.PREPARE)):
            if error(StepKey.PREPARE):
                prepare = (StepState.FAILED, error(StepKey.PREPARE))
            elif not planned.repository and not root:
                prepare = (StepState.SKIPPED, NO_REPOSITORY)
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
        steps.append((StepKey.VERIFY, *((StepState.SKIPPED, "") if skipped(StepKey.VERIFY) else self._verify(session, done))))
        if (after := self._after_step(plan, name, done)):
            steps.append(after)
        final = StepState.DONE if done else StepState.YOU if task.status is TaskStatus.TO_VERIFY else StepState.TODO
        steps.append((StepKey.FINAL, final, ""))
        return _path_steps(steps)

    def _after_step(self, plan: ActivityPlan, name: str, done: bool) -> tuple[StepKey, StepState, str] | None:
        """The step of the automation after the verification; None when the activity has none and none ran."""
        key_id = step_id(name, StepKey.AFTER)
        run_id = plan.automation_runs.get(key_id)
        if plan.after_automation is None and run_id is None:
            return None
        if key_id in plan.skipped:
            return StepKey.AFTER, StepState.SKIPPED, ""
        if plan.errors.get(key_id):
            return StepKey.AFTER, StepState.FAILED, plan.errors[key_id]
        run = self._pipelines.get_pipeline_run(run_id) if run_id is not None and self._pipelines else None
        if run is None:
            return StepKey.AFTER, StepState.SKIPPED if done else StepState.TODO, ""
        if run.status is RunStatus.DONE:
            return StepKey.AFTER, StepState.DONE, ""
        if run.status is RunStatus.FAILED:
            return StepKey.AFTER, StepState.FAILED, run.error or "fallita"
        return StepKey.AFTER, StepState.RUNNING, ""

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
        """«▶️ Avvia» (``paused`` False) or «⏸ Pausa»: the round of the activity's tasks."""
        return self._plans.save(self._with_tasks(project_name, activity_name).model_copy(update={"paused": paused}))

    def set_options(self, project_name: str, activity_name: str, options: PlanOptions) -> ActivityPlan:
        """How the round goes: the preparation before delegating, the automation after the verification
        (both of this project) and the automatic ok to Copilot's plan."""
        plan = self.plan(project_name, activity_name)
        if options.prepare not in (PREPARE_NONE, PREPARE_DEV):
            self._automation_of(project_name, options.prepare[len(AUTOMATION):] if options.prepare.startswith(AUTOMATION) else "",
                                f"Preparazione non valida: {options.prepare}")
        if options.after_automation is not None:
            self._automation_of(project_name, str(options.after_automation), f"Automation non trovata nel progetto: {options.after_automation}")
        return self._plans.save(plan.model_copy(update=options.model_dump()))

    def _automation_of(self, project_name: str, automation: str, message: str) -> None:
        pipeline = self._pipelines.get_pipeline(int(automation)) if automation.isdigit() and self._pipelines else None
        if pipeline is None or pipeline.project_name != project_name:
            raise ValidationError(message)

    def skip(self, project_name: str, activity_name: str, task: str, step: StepKey) -> ActivityPlan:
        """Skip a step of a task (preparation, verification, automation after it): the round goes on without it."""
        plan = self._step_of(project_name, activity_name, task, step, SKIPPABLE, "saltare")
        key = step_id(task, step)
        errors = {item: text for item, text in plan.errors.items() if item != key}
        return self._plans.save(plan.model_copy(update={"skipped": [*dict.fromkeys([*plan.skipped, key])], "errors": errors}))

    def retry(self, project_name: str, activity_name: str, task: str, step: StepKey) -> ActivityPlan:
        """Run a failed step again: the preparation, the delegation and the automation at the round's next turn, the tests now."""
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

    def _with_tasks(self, project_name: str, activity_name: str) -> ActivityPlan:
        plan = self._plans.latest(project_name, note_file_name(activity_name))
        if plan is None or not plan.tasks:
            raise ConflictError("L'attività non ha ancora task: creali allo step Pianifica.")
        return plan

    def _step_of(self, project_name: str, activity_name: str, task: str, step: StepKey, allowed: set[StepKey], what: str) -> ActivityPlan:
        plan = self._with_tasks(project_name, activity_name)
        if not any(item.task == task for item in plan.tasks):
            raise NotFoundError(f"Il task {task} non è nel piano.")
        if step not in allowed:
            raise ValidationError(f"Non si può {what} il passo «{STEP_LABELS[step]}».")
        return plan

    # ----------------------------------------------------------------- round
    def advance_all(self) -> int:
        """The worker's turn: every running round one step on where it can. Returns how many steps it took."""
        moved = 0
        for plan in self._plans.running():
            try:
                moved += self.advance(plan)
            except Exception:  # noqa: BLE001 - one broken round never stops the others
                log_exception(LogPrefix.PLAN_SERVICE, "Giro di %s · %s non avanzato", plan.project_name, plan.activity)
        return moved

    def advance(self, plan: ActivityPlan) -> int:
        """At the current task: prepare and delegate it, give the ok to Copilot's plan (with ``auto_approve``),
        run the automation after the verification. 1 when it did something; the rest waits for the user."""
        if plan.paused or not plan.tasks or self._copilot is None:
            return 0
        current = next((item for item in self._tasks(plan) if item.current), None)
        if current is None or not TaskStatus(current.status).is_refined:
            return 0
        states = {step.key: step.state for step in current.steps}
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
            self._run_after(plan, current, plan.after_automation)
            return 1
        return 0

    def _delegate(self, plan: ActivityPlan, current: PathTask) -> None:
        """Preparation (as the activity says) and delegation with Copilot's default prompt and model; a failure is the step's error."""
        assert self._copilot is not None
        targets: list[PrepareTarget] = []
        automation: LearnedPreparation | None = None
        prepare = next((step for step in current.steps if step.key is StepKey.PREPARE), None)
        how = PREPARE_NONE if current.type.plan_only or prepare is None or prepare.state is StepState.SKIPPED else plan.prepare
        if how != PREPARE_NONE:
            fields = self._fields_for(plan, current.task, current.repository, StepKey.PREPARE)
            if how == PREPARE_DEV:
                branch = fields.get("branch") or self._resolve(DEFAULT_FIELDS["branch"], plan, current.task, current.repository)
                targets = [PrepareTarget(repository=current.repository, branch=branch, base=fields.get("base", ""))]
            elif how.startswith(AUTOMATION) and how[len(AUTOMATION):].isdigit():
                automation = LearnedPreparation(automation_id=int(how[len(AUTOMATION):]), fields=fields)
        try:
            self._copilot.start(plan.project_name, current.task, current.repository, prepare=targets, learned=automation)
        except AppError as exc:
            key = StepKey.PREPARE if str(exc).startswith(PREPARE_FAILED) else StepKey.DELEGATE
            self._plans.save(plan.model_copy(update={"errors": {**plan.errors, step_id(current.task, key): str(exc)}}))

    # ---------------------------------------------------------------- fields
    def _automation_of_step(self, plan: ActivityPlan, step: StepKey) -> tuple[str, list[str]]:
        """What runs at ``step`` (prepare or after) and its fields; ``("", [])`` = nothing."""
        if step is StepKey.PREPARE:
            if plan.prepare == PREPARE_DEV:
                return PREPARE_AUTOMATION, DEV_FIELDS
            automation = plan.prepare[len(AUTOMATION):] if plan.prepare.startswith(AUTOMATION) else ""
        else:
            automation = str(plan.after_automation) if plan.after_automation is not None else ""
        pipeline = self._pipelines.get_pipeline(int(automation)) if automation.isdigit() and self._pipelines else None
        return (pipeline.name, list(pipeline.fields)) if pipeline else ("", [])

    def _resolve(self, template: str, plan: ActivityPlan, task: str, repository: str) -> str:
        values = {"task": task.removeprefix("agent-task-").removesuffix(".md"), "note": task, "repository": repository}
        if "{base}" in template:
            try:
                values["base"] = self._git.branches(plan.project_name, repository).current or ""
            except AppError:  # no repository there (a task without one): no base
                values["base"] = ""
        for key, value in values.items():
            template = template.replace("{" + key + "}", value)
        return template

    def _fields_for(self, plan: ActivityPlan, task: str, repository: str, step: StepKey) -> dict[str, str]:
        """The fields of ``step`` for ``task``: its own ones, else the activity's template resolved for it."""
        _, names = self._automation_of_step(plan, step)
        own = plan.task_fields.get(step_id(task, step), {})
        template = plan.prepare_fields if step is StepKey.PREPARE else plan.after_fields
        return {name: own[name] if name in own else self._resolve(template.get(name, DEFAULT_FIELDS.get(name, "")), plan, task, repository)
                for name in names}

    def task_fields(self, project_name: str, activity_name: str, task: str, step: StepKey) -> TaskFields:
        """«⚙️ Campi» of a task: what runs at ``step`` and its fields, resolved for the task."""
        plan = self._step_of(project_name, activity_name, task, step, {StepKey.PREPARE, StepKey.AFTER}, "dare i campi a")
        planned = next(item for item in plan.tasks if item.task == task)
        automation, _ = self._automation_of_step(plan, step)
        return TaskFields(task=task, step=step.value, automation=automation, fields=self._fields_for(plan, task, planned.repository, step),
                          own=step_id(task, step) in plan.task_fields)

    def set_task_fields(self, project_name: str, activity_name: str, task: str, step: StepKey, fields: dict[str, str]) -> ActivityPlan:
        """The task's own fields for ``step`` (empty = back to the activity's template)."""
        plan = self._step_of(project_name, activity_name, task, step, {StepKey.PREPARE, StepKey.AFTER}, "dare i campi a")
        key = step_id(task, step)
        others = {item: values for item, values in plan.task_fields.items() if item != key}
        return self._plans.save(plan.model_copy(update={"task_fields": {**others, key: dict(fields)} if fields else others}))

    def _run_after(self, plan: ActivityPlan, current: PathTask, automation: int) -> None:
        """The automation after the verification, now (no LLM): its fields from the task, else «<repository> <task>»."""
        key_id = step_id(current.task, StepKey.AFTER)
        try:
            if self._checks is None or self._pipelines is None:
                raise ValidationError("Le automation del giro non sono disponibili in questo processo.")
            pipeline = self._pipelines.get_pipeline(automation)
            if pipeline is not None and pipeline.fields:
                text = json.dumps(self._fields_for(plan, current.task, current.repository, StepKey.AFTER))
            else:
                text = f"{current.repository or '.'} {current.task}"
            check = self._checks.run_automation(plan.project_name, automation, text)
        except AppError as exc:
            self._plans.save(plan.model_copy(update={"errors": {**plan.errors, key_id: str(exc)}}))
            return
        self._plans.save(plan.model_copy(update={"automation_runs": {**plan.automation_runs, key_id: check.run_id}}))

    def _summary(self, plan: ActivityPlan, tasks: list[PathTask]) -> str:
        """What the round did, composed by the code: tasks, files changed, steps skipped, cost."""
        lines = [f"Task fatti: {len([item for item in tasks if item.status == TaskStatus.DONE.value])} di {len(tasks)}"]
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


def _path_steps(steps: list[tuple[StepKey, StepState, str]]) -> list[PathStep]:
    return [PathStep(key=key, label=STEP_LABELS[key], state=state, detail=detail) for key, state, detail in steps]


def model_input(activity: Activity, items: dict[int, str], repositories: list[str], context: list[str], references: list[str] | None = None) -> str:
    """The text the Pianificatore gets, before masking."""
    lines = [f"Attività: {activity.title}"]
    if activity.description.strip():
        lines.append(activity.description.strip())
    if references:
        lines.append("Riferimenti: " + ", ".join(references))
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
