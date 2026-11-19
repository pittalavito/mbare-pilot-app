"""The plan of an activity and its round (plan 18): steps «Pianifica» and «Lavora».

1. **Propose** («✨ Proponi i task»): **one call** to the agent ``pianificatore``
   of global-agent.yml with a **structured answer** (``PlanAnswer``), no tools,
   few tokens: the activity's title, description and items not done and
   without a task (numbered), the titles of its references, the project's
   repositories, the task types, the project's development rules
   (``context/sviluppo.md``, plan 22) and the 3 nearest pieces of the context
   index. Around each development it proposes a **pre** and a **post
   development** task with their steps. Masked like «Elabora WIP»; the
   proposals come back in clear. A proposal on items that do not exist loses
   them; one without items is «new». The activity has **one plan**: the
   proposals wait in it next to the tasks already created.
2. **Create** (no LLM): the chosen proposals, as corrected, and the tasks
   written by hand, in the given order, become agent tasks **«to do»** with
   objective, criteria and steps, linked to their items (a new one gets its
   item first) and to the activity, appended to the plan's tasks. The activity
   goes «in progress».
3. **Path** (no LLM): for each task its steps, derived from the task's status
   and its latest Copilot session: delegation, Copilot's plan, execution, final
   confirmation (developments), or Copilot's answer (the types that do not
   change the code), or «Automatico o a mano» (pre/post development: never Copilot; plan 25).
   The steps waiting for the user are the control points.
4. **Round** (the worker, no LLM of its own): started with «▶️ Avvia», stopped
   with «⏸ Pausa». At the current task (a task moved back to refinement waits)
   it delegates with Copilot's defaults and gives the ok to Copilot's plan only
   with ``auto_approve``. A pre/post development task waits for «✅ Fatto»
   (``mark_done``). Nothing runs by itself before or after Copilot (plan 22).
5. Once no task is left, the **summary** composed by the code (step «Chiudi»)."""
import copy
import json

from datapizza.tools import Tool
from pydantic import BaseModel

from core.error import AppError, ConflictError, NotFoundError, UpstreamError, ValidationError
from core.observability import LogPrefix, log_exception, observed
from domain.agent.outputs import PLAN, PLAN_AGENT
from domain.masking.preview import masked_text, unmask
from domain.project.data_paths import note_file_name
from models.domain.agent import RunOrigin
from models.domain.copilot import CopilotSession, CopilotSessionStatus
from models.domain.masking import MaskCategory
from models.domain.note import Activity, ActivityStatus, AgentTask, ChecklistItem, TaskStatus, TaskType, TodoItem
from models.domain.plan import (
    RETRYABLE,
    STEP_LABELS,
    ActivityPath,
    ActivityPlan,
    OperationState,
    PathStep,
    PathTask,
    PlanAnswer,
    PlanChoice,
    PlanOptions,
    PlanProposal,
    PlanTask,
    StepKey,
    StepState,
    step_id,
)
from service.copilot_service import CopilotService
from service.git_service import GitService
from service.masking_service import MaskingService
from service.pipeline_service import PipelineService
from service.project_data_service import ProjectDataService
from service.rag_service import RagService
from service.store.plan_store import PlanStore
from service.structured_agent_service import StructuredAgentService
from tool.context import ToolContext
from tool.registry import TOOL_REGISTRY

CONTEXT_PIECES = 3
"""How many pieces of the context index the Pianificatore reads."""
_PIECE_CHARS = 500
RULES_DOCUMENT = "sviluppo.md"
"""The project's development rules (context/sviluppo.md): what to do before and after each development."""
_RULES_CHARS = 4000
TYPE_WORDS = {TaskType.DEVELOPMENT: "sviluppo", TaskType.ANALYSIS: "analisi", TaskType.CONFLUENCE: "Confluence", TaskType.JIRA: "Jira",
              TaskType.PRE_DEV: "pre sviluppo", TaskType.POST_DEV: "post sviluppo"}
_TYPES = ("pre_dev (prima di uno sviluppo: branch, aggiornamento, build), development (cambia il codice), post_dev (dopo uno sviluppo: "
          "pulizia della cartella mbare-pilot/<task>/, test, commit), analysis (analisi del codice), confluence (pagina Confluence), jira (issue Jira)")
_DEFAULT_RULES = ("Nessuna regola scritta: prima di ogni sviluppo un pre_dev (branch feature/<task> dal branch corrente, aggiornato, build), "
                  "dopo ogni sviluppo un post_dev (togli la cartella mbare-pilot/<task>/, lancia i test).")


class PlanService:

    def __init__(self, project_data: ProjectDataService, masking: MaskingService, agents: StructuredAgentService,
                 plans: PlanStore, git: GitService, rag: RagService | None = None,
                 copilot: CopilotService | None = None, pipelines: PipelineService | None = None):
        self._data = project_data
        self._masking = masking
        self._agents = agents
        self._plans = plans
        self._git = git
        self._rag = rag
        self._copilot = copilot
        self._pipelines = pipelines

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
        automations = self._automations(project_name)
        masked = masked_text(model_input(activity, open_items, repositories, self._context(project_name, activity), references,
                                         self._rules(project_name), automations), entries)
        call = self._agents.call(agent, masked.text, self._tools(project_name, agent.tool_names, entries))

        clear = lambda text: unmask(text, entries, masked.temporary).strip()  # noqa: E731
        answer = call.answer if isinstance(call.answer, PlanAnswer) else None
        proposals = to_proposals(answer, open_items, repositories, clear, list(automations)) if answer else []
        run_id = self._agents.save(call, project_name=project_name, origin=RunOrigin.PLAN, input=unmask(masked.text, entries, masked.temporary),
                                   output=json.dumps([proposal.model_dump(mode="json") for proposal in proposals], ensure_ascii=False))
        if call.error is not None:
            raise UpstreamError(f"Il Pianificatore non ha risposto: {call.error}")
        return self._plans.save(plan.model_copy(update={
            "run_id": run_id, "proposals": proposals, "cost_eur": round(plan.cost_eur + call.telemetry.total_tokens.cost_eur, 6)}))

    def _tools(self, project_name: str, names: list[str], entries) -> list[Tool]:
        """The Pianificatore's tools (``search_context``, plan 26) when its YAML has them and the project has an index;
        what they give back is masked like its input."""
        if self._rag is None or "search_context" not in names:
            return []
        tool = TOOL_REGISTRY["search_context"].build(ToolContext(project_name=project_name, git=self._git, rag=self._rag))
        original = tool.func

        def masked(*args, **kwargs):
            result = original(*args, **kwargs)
            text = result.model_dump_json() if isinstance(result, BaseModel) else str(result)
            return masked_text(text, entries).text

        wrapped = copy.copy(tool)
        wrapped.func = masked
        return [wrapped]

    def _automations(self, project_name: str) -> dict[str, str]:
        """The project's automations that can be started, name → description (the Pianificatore picks one for a pre/post task)."""
        if self._pipelines is None:
            return {}
        return {pipeline.name: pipeline.description for pipeline in self._pipelines.runnable_pipelines(project_name)}

    def _reference_titles(self, project_name: str, activity: Activity) -> list[str]:
        """The titles of the activity's references; one that is gone is left out."""
        titles = []
        for name in activity.references:
            try:
                titles.append(self._data.reference(project_name, name)[1].title)
            except AppError:
                continue
        return titles

    def _rules(self, project_name: str) -> str:
        """The project's development rules (context/sviluppo.md); ``""`` without the document."""
        try:
            return self._data.read_context(project_name, RULES_DOCUMENT).strip()[:_RULES_CHARS]
        except AppError:
            return ""

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
                criteria=[ChecklistItem(text=text.strip()) for text in choice.criteria if text.strip()], references=activity.references,
                **_operation_fields(choice)))
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
        result = [self._path_task(plan, planned, tasks.get(planned.task), next((item for item in sessions if item.task_note == planned.task), None))
                  for planned in plan.tasks]
        current = next((item for item in result if item.status not in (TaskStatus.DONE.value, "missing")), None)
        if current is not None:
            current.current = True
        return result

    def _path_task(self, plan: ActivityPlan, planned: PlanTask, task: AgentTask | None, session: CopilotSession | None) -> PathTask:
        if task is None:
            return PathTask(task=planned.task, title=planned.task, type=TaskType.DEVELOPMENT, status="missing", repository=planned.repository)
        return PathTask(task=planned.task, title=task.title, type=task.type, status=task.status.value, repository=planned.repository,
                        session_id=session.id if session else None, steps=self._steps(plan, planned, task, session))

    def _steps(self, plan: ActivityPlan, planned: PlanTask, task: AgentTask, session: CopilotSession | None) -> list[PathStep]:
        done = task.status is TaskStatus.DONE
        if task.type.operations:  # «🤖 Automatico» or by hand, then «Fatto»
            run = plan.operations.get(planned.task)
            state = StepState.DONE if done else {OperationState.QUEUED: StepState.RUNNING, OperationState.RUNNING: StepState.RUNNING,
                                                  OperationState.FAILED: StepState.FAILED}.get(run.state, StepState.YOU) if run else StepState.YOU
            return _path_steps([(StepKey.OPERATION, state, run.error if run and state is StepState.FAILED else "")])
        steps: list[tuple[StepKey, StepState, str]] = []
        error = plan.errors.get(step_id(planned.task, StepKey.DELEGATE), "")
        if error:
            steps.append((StepKey.DELEGATE, StepState.FAILED, error))
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
        final = StepState.DONE if done else StepState.YOU if task.status is TaskStatus.TO_VERIFY else StepState.TODO
        steps.append((StepKey.FINAL, final, ""))
        return _path_steps(steps)

    # ------------------------------------------------------------- controls
    def set_paused(self, project_name: str, activity_name: str, paused: bool) -> ActivityPlan:
        """«▶️ Avvia» (``paused`` False) or «⏸ Pausa»: the round of the activity's tasks."""
        return self._plans.save(self._with_tasks(project_name, activity_name).model_copy(update={"paused": paused}))

    def set_options(self, project_name: str, activity_name: str, options: PlanOptions) -> ActivityPlan:
        """How the round goes: the automatic ok to Copilot's plan."""
        return self._plans.save(self.plan(project_name, activity_name).model_copy(update=options.model_dump()))

    def retry(self, project_name: str, activity_name: str, task: str, step: StepKey) -> ActivityPlan:
        """Run a failed delegation again, at the round's next turn."""
        plan = self._step_of(project_name, activity_name, task, step, RETRYABLE, "riprovare")
        key = step_id(task, step)
        return self._plans.save(plan.model_copy(update={"errors": {item: text for item, text in plan.errors.items() if item != key}}))

    def mark_done(self, project_name: str, activity_name: str, task: str) -> ActivityPlan:
        """«✅ Fatto» on a pre/post development task: done by Dev or by hand, the round goes on."""
        plan = self._step_of(project_name, activity_name, task, StepKey.OPERATION, {StepKey.OPERATION}, "chiudere")
        current = self._data.agent_task(project_name, task)
        if not current.type.operations:
            raise ValidationError("«Fatto» vale solo per un task pre o post sviluppo: gli altri li chiude il loro passo.")
        if current.status is not TaskStatus.DONE:
            self._data.save_agent_task(project_name, task, current.model_copy(update={"status": TaskStatus.DONE}))
        return plan

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
        """At the current task: delegate it and give the ok to Copilot's plan (with ``auto_approve``).
        1 when it did something; the rest waits for the user (a pre/post development task: «Fatto»)."""
        if plan.paused or not plan.tasks or self._copilot is None:
            return 0
        current = next((item for item in self._tasks(plan) if item.current), None)
        if current is None or not TaskStatus(current.status).is_refined:
            return 0
        states = {step.key: step.state for step in current.steps}
        if states.get(StepKey.DELEGATE) is StepState.TODO:
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
        return 0

    def _delegate(self, plan: ActivityPlan, current: PathTask) -> None:
        """Delegation with Copilot's default prompt and model; a failure is the step's error.
        A task without code and without a repository goes without one (Copilot in the project's data, plan 21)."""
        assert self._copilot is not None
        try:
            self._copilot.start(plan.project_name, current.task, current.repository,
                                no_repository=current.type.plan_only and not current.repository)
        except AppError as exc:
            self._plans.save(plan.model_copy(update={"errors": {**plan.errors, step_id(current.task, StepKey.DELEGATE): str(exc)}}))

    def set_task_repository(self, project_name: str, task: str, repository: str) -> None:
        """The task's repository in the plans that hold it (the delegation's repository
        changed, plan 21)."""
        name = note_file_name(task)
        for plan in self._plans.latest_per_activity(project_name):
            if any(note_file_name(planned.task) == name and planned.repository != repository for planned in plan.tasks):
                tasks = [planned.model_copy(update={"repository": repository}) if note_file_name(planned.task) == name else planned
                         for planned in plan.tasks]
                self._plans.save(plan.model_copy(update={"tasks": tasks}))

    def _summary(self, plan: ActivityPlan, tasks: list[PathTask]) -> str:
        """What the round did, composed by the code: tasks, files changed, cost."""
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


def _operation_fields(choice: PlanChoice) -> dict:
    """Steps, commands and automation: only a pre/post development task has them."""
    if not choice.type.operations:
        return {}
    clean = lambda values: [value.strip() for value in values if value.strip()]  # noqa: E731
    return {"steps": clean(choice.steps), "commands": clean(choice.commands), "automation": choice.automation.strip()}


def model_input(activity: Activity, items: dict[int, str], repositories: list[str], context: list[str], references: list[str] | None = None,
                rules: str = "", automations: dict[str, str] | None = None) -> str:
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
    lines.append(f"\nRegole di sviluppo del progetto (prima e dopo ogni sviluppo):\n{rules}" if rules else f"\n{_DEFAULT_RULES}")
    lines.append("\nAutomation del progetto (per pre_dev e post_dev):")
    lines += [f"- {name}: {' '.join(description.split())}" if description.strip() else f"- {name}" for name, description in (automations or {}).items()] or [
        "(nessuna)"]
    if context:
        lines.append("\nContesto del progetto:")
        lines += [f"- {piece}" for piece in context]
    return "\n".join(lines)


def to_proposals(answer: PlanAnswer, items: dict[int, str], repositories: list[str], clear, automations: list[str] | None = None) -> list[PlanProposal]:
    """The answer in clear; items not in the list are dropped (a task left without any is «new»),
    a repository or an automation not in the project is left empty, a task without a title is dropped."""
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
            steps=[clear(text) for text in raw.steps if text.strip()] if raw.type.operations else [],
            commands=[clear(text) for text in raw.commands if text.strip()] if raw.type.operations else [],
            automation=automation if raw.type.operations and (automation := clear(raw.automation)) in (automations or []) else "",
        ))
    return proposals
