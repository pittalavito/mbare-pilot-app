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
   confirmation. The steps waiting for the user are the control points."""
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
from models.domain.dev import VERIFY_FAILED, VERIFY_OK
from models.domain.masking import MaskCategory
from models.domain.note import Activity, AgentTask, ChecklistItem, TaskStatus, TaskType, TodoItem
from models.domain.plan import (
    STEP_LABELS,
    ActivityPath,
    ActivityPlan,
    PathStep,
    PathTask,
    PlanAnswer,
    PlanChoice,
    PlanProposal,
    PlanStatus,
    PlanTask,
    StepKey,
    StepState,
)
from service.chat_service import ChatService
from service.copilot_service import CopilotService
from service.git_service import GitService
from service.masking_service import MaskingService
from service.model_service import require_usable_model
from service.project_data_service import ProjectDataService
from service.rag_service import RagService
from service.store.catalog_store import CatalogStore
from service.store.chatbot_store import ChatbotStore
from service.store.plan_store import PlanStore
from service.store.run_store import RunStore

CONTEXT_PIECES = 3
"""How many pieces of the context index the Pianificatore reads."""
_PIECE_CHARS = 500
_TYPES = "development (cambia il codice), analysis (analisi del codice), confluence (pagina Confluence), jira (issue Jira)"


class PlanService:

    def __init__(self, project_data: ProjectDataService, masking: MaskingService, chatbots: ChatbotStore, chat: ChatService,
                 catalog: CatalogStore, runs: RunStore, plans: PlanStore, git: GitService, rag: RagService | None = None,
                 copilot: CopilotService | None = None):
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
        tasks = dict(self._data.agent_tasks(project_name))
        sessions = self._copilot.sessions(project_name) if self._copilot else []
        result = [self._path_task(planned, tasks.get(planned.task), next((item for item in sessions if item.task_note == planned.task), None))
                  for planned in plan.tasks]
        current = next((item for item in result if item.status not in (TaskStatus.DONE.value, "missing")), None)
        if current is not None:
            current.current = True
        return ActivityPath(plan=plan, tasks=result)

    def confirm_task(self, project_name: str, task_note: str) -> None:
        """«Conferma del task»: objective and criteria are fine, the task is «to do» (ready to delegate)."""
        name = note_file_name(task_note)
        task = self._data.agent_task(project_name, name)
        if task.status.is_refined:
            raise ConflictError("Il task è già confermato.")
        if not task.objective.strip():
            raise ValidationError("Il task non ha un obiettivo: scrivilo (o chiedi al Refiner) prima di confermarlo.")
        self._data.save_agent_task(project_name, name, task.model_copy(update={"status": TaskStatus.TODO}))

    def _path_task(self, planned: PlanTask, task: AgentTask | None, session: CopilotSession | None) -> PathTask:
        if task is None:
            return PathTask(task=planned.task, title=planned.task, type=TaskType.DEVELOPMENT, status="missing", repository=planned.repository)
        return PathTask(task=planned.task, title=task.title, type=task.type, status=task.status.value, repository=planned.repository,
                        session_id=session.id if session else None, steps=self._steps(task, session))

    def _steps(self, task: AgentTask, session: CopilotSession | None) -> list[PathStep]:
        done = task.status is TaskStatus.DONE
        steps = [(StepKey.CONFIRM, StepState.DONE if task.status.is_refined else StepState.YOU, "")]
        steps.append((StepKey.DELEGATE, StepState.DONE if session or done else StepState.TODO, session.repository if session else ""))
        status = session.status if session else None
        if task.type.plan_only:
            answer = StepState.DONE if done else StepState.YOU if status is CopilotSessionStatus.PLANNING else (
                StepState.FAILED if status in (CopilotSessionStatus.FAILED, CopilotSessionStatus.CANCELLED) else StepState.TODO)
            steps.append((StepKey.ANSWER, answer, ""))
            return _path_steps(steps)
        if status is None:
            plan = StepState.DONE if done else StepState.TODO
        else:
            plan = StepState.YOU if status is CopilotSessionStatus.PLANNING else StepState.DONE
        steps.append((StepKey.COPILOT_PLAN, plan, ""))
        execution = {CopilotSessionStatus.QUEUED: StepState.RUNNING, CopilotSessionStatus.RUNNING: StepState.RUNNING,
                     CopilotSessionStatus.DONE: StepState.DONE, CopilotSessionStatus.FAILED: StepState.FAILED,
                     CopilotSessionStatus.CANCELLED: StepState.FAILED}.get(status, StepState.DONE if done else StepState.TODO) if status else (
            StepState.DONE if done else StepState.TODO)
        steps.append((StepKey.EXECUTION, execution, session.error or "" if session else ""))
        steps.append((StepKey.VERIFY, *self._verify(session, done)))
        final = StepState.DONE if done else StepState.YOU if task.status is TaskStatus.TO_VERIFY else StepState.TODO
        steps.append((StepKey.FINAL, final, ""))
        return _path_steps(steps)

    def _verify(self, session: CopilotSession | None, done: bool) -> tuple[StepState, str]:
        """From the session's latest verification event: ok, failed, or skipped (no «Verifica sviluppo» ran)."""
        if session is None or session.status is not CopilotSessionStatus.DONE or self._copilot is None or session.id is None:
            return (StepState.DONE if done else StepState.TODO), ""
        events = [message.content for message in self._copilot.messages(session.id) if message.role is CopilotMessageRole.EVENT]
        verification = next((text for text in reversed(events) if text.startswith((VERIFY_OK, VERIFY_FAILED))), None)
        if verification is None:
            return StepState.SKIPPED, ""
        return (StepState.DONE, "") if verification.startswith(VERIFY_OK) else (StepState.FAILED, "test falliti")


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
