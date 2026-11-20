"""Step «Chiudi» of an activity.

- **Proposal** (``propose_learned``): **one call** to the agent ``imparato`` of
  global-agent.yml (structured answer ``LearnedAnswer``, no tools): the
  activity's title and description, its tasks and the round's summary,
  masked; a few points to remember, in clear, for the user to correct.
- **Close** (``close``): what was learned goes in the project's context
  document ``context/imparato.md`` **by theme**: each point
  («Tema: testo», one per line; no theme = «Generale») at the top of its
  ``## <tema>`` section (made when missing), with the activity and the date;
  the document is then indexed for the agents with ``search_context``. Nothing learned = the
  document is not touched. The activity becomes «done» and its round stops.
- **Reopen** (``reopen``): back to «in progress»; the section already written
  stays (the document is a diary: corrected by hand from the Contesto section).
- **Archive** (``archive``): a done activity becomes a summary note
  ``archivio-<attività>.md`` (description, items, tasks with their outcome and
  the pages and issues they made); the activity, its tasks, their answers and
  drafts, its plan and the tasks' Copilot sessions are deleted, and the
  references the user chose."""
import json
from datetime import date

from core.error import ConflictError, NotFoundError, UpstreamError
from core.observability import LogPrefix, observed
from domain.agent.outputs import LEARNED, LEARNED_AGENT
from domain.masking.preview import masked_text, unmask
from domain.project.data_paths import note_file_name, slug
from models.domain.activity_close import ActivityArchived, ActivityClosed, LearnedAnswer, LearnedDraft, LearnedPoint
from models.domain.agent import RunOrigin
from models.domain.note import ActivityStatus, TaskStatus
from service.copilot_service import CopilotService, output_note_name
from service.masking_service import MaskingService
from service.plan_service import PlanService
from service.project_data_service import ProjectDataService
from service.rag_service import RagService
from service.store.plan_store import PlanStore
from service.structured_agent_service import StructuredAgentService

LEARNED_DOCUMENT = "imparato.md"
"""The context document of what the activities taught."""
LEARNED_HEADER = "# Imparato\n\nQuello che le attività del progetto hanno insegnato, per tema; in ogni tema i punti più recenti in cima."
GENERAL_THEME = "Generale"
_THEME_CHARS = 40


class ActivityCloseService:

    def __init__(self, project_data: ProjectDataService, masking: MaskingService, agents: StructuredAgentService, plan: PlanService,
                 plans: PlanStore, rag: RagService | None = None, copilot: CopilotService | None = None):
        self._data = project_data
        self._masking = masking
        self._agents = agents
        self._plan = plan
        self._plans = plans
        self._rag = rag
        self._copilot = copilot

    @observed(LogPrefix.CLOSE_SERVICE)
    def propose_learned(self, project_name: str, activity_name: str) -> LearnedDraft:
        """The points the agent ``imparato`` proposes from the activity, its tasks and the round's summary."""
        name = note_file_name(activity_name)
        activity = self._data.activity(project_name, name)
        path = self._plan.path(project_name, name)
        lines = [f"Attività: {activity.title}"]
        if activity.description.strip():
            lines.append(activity.description.strip())
        if path.tasks:
            lines.append("\nTask:")
            lines += [f"- {task.title} ({task.type.value}, {task.status})" for task in path.tasks]
        if path.summary:
            lines.append(f"\nRiepilogo:\n{path.summary}")
        agent = self._agents.agent(LEARNED_AGENT, LEARNED)
        entries = self._masking.entries(project_name)
        masked = masked_text("\n".join(lines), entries)
        call = self._agents.call(agent, masked.text)
        answer = call.answer if isinstance(call.answer, LearnedAnswer) else None
        clear = lambda text: unmask(text, entries, masked.temporary).strip()  # noqa: E731
        points = [LearnedPoint(theme=clear(point.theme) or GENERAL_THEME, text=clear(point.text)) for point in answer.points
                  if clear(point.text)] if answer else []
        run_id = self._agents.save(call, project_name=project_name, origin=RunOrigin.LEARNED, input=unmask(masked.text, entries, masked.temporary),
                                   output=json.dumps([point.model_dump() for point in points], ensure_ascii=False))
        if call.error is not None:
            raise UpstreamError(f"L'agente {agent.name} non ha risposto: {call.error}")
        return LearnedDraft(points=points, run_id=run_id, cost_eur=round(call.telemetry.total_tokens.cost_eur, 6))

    @observed(LogPrefix.CLOSE_SERVICE)
    def close(self, project_name: str, activity_name: str, learned: str, today: date | None = None) -> ActivityClosed:
        """What was learned in context/imparato.md by theme (when there is something), then the activity done and its round stopped."""
        name = note_file_name(activity_name)
        activity = self._data.activity(project_name, name)
        points = parse_points(learned)
        written, index_error = None, None
        if points:
            when = (today or date.today()).strftime("%d/%m/%Y")
            document = self._learned_document(project_name)
            for point in reversed(points):  # the first ends at the top of its theme
                document = with_point(document, point.theme, f"{point.text} ({activity.title}, {when})")
            self._data.save_context(project_name, LEARNED_DOCUMENT, document)
            written = LEARNED_DOCUMENT
            index_error = self._rag.index_quietly(project_name, LEARNED_DOCUMENT) if self._rag else None
        self._data.save_activity(project_name, name, activity.model_copy(update={"status": ActivityStatus.DONE}))
        plan = self._plans.latest(project_name, name)
        if plan is not None and not plan.paused:
            self._plans.save(plan.model_copy(update={"paused": True}))
        return ActivityClosed(activity=name, context=written, index_error=index_error)

    def reopen(self, project_name: str, activity_name: str) -> None:
        """Back to «in progress» (step «Pianifica»); context/imparato.md is not touched."""
        name = note_file_name(activity_name)
        activity = self._data.activity(project_name, name)
        self._data.save_activity(project_name, name, activity.model_copy(update={"status": ActivityStatus.IN_PROGRESS}))

    @observed(LogPrefix.CLOSE_SERVICE)
    def archive(self, project_name: str, activity_name: str, delete_references: list[str], today: date | None = None) -> ActivityArchived:
        """A done activity into ``archivio-<attività>.md``; the rest deleted, the references in ``delete_references`` too."""
        name = note_file_name(activity_name)
        activity = self._data.activity(project_name, name)
        if activity.status is not ActivityStatus.DONE:
            raise ConflictError("Si archivia un'attività chiusa: prima «✅ Chiudi attività».")
        plan = self._plans.latest(project_name, name)
        tasks = list(dict.fromkeys([*activity.agent_tasks, *(item.task for item in plan.tasks)] if plan else activity.agent_tasks))
        found = dict(self._data.agent_tasks(project_name))
        references = {ref_name: reference for ref_name, _, reference in self._data.references(project_name)}
        lines = [f"# Archivio: {activity.title}", "", f"Archiviata il {(today or date.today()):%d/%m/%Y}."]
        if activity.description.strip():
            lines += ["", "## Descrizione", activity.description.strip()]
        if activity.items:
            lines += ["", "## Voci", *(f"- [{'x' if item.done else ' '}] {item.text}" for item in activity.items)]
        if tasks:
            lines += ["", "## Task"]
            for task_name in tasks:
                task = found.get(task_name)
                if task is None:
                    continue
                made = [f"[{references[ref].title}]({references[ref].source_url})" for ref in task.references
                        if ref in references and references[ref].source_url.startswith("http")]
                lines.append(f"- {'✓' if task.status is TaskStatus.DONE else '…'} {task.title} ({task.type.value})"
                             + (f" · {', '.join(made)}" if made else ""))
        for task_name in tasks:  # nothing deleted if a Copilot session is still running
            if self._copilot is not None and task_name in found:
                self._copilot.check_no_running(project_name, task_name)
        note = note_file_name(f"archivio-{slug(activity.title, 'attivita')}")
        self._data.save_note(project_name, note, "\n".join(lines) + "\n")
        deleted: list[str] = []
        for task_name in tasks:
            if task_name not in found:
                continue
            if self._copilot is not None:
                self._copilot.delete_task_sessions(project_name, task_name)
            answer = output_note_name(task_name, found[task_name].type) if found[task_name].type.plan_only else ""
            for gone in ([answer] if answer and self._data.note_exists(project_name, answer) else []) + [task_name]:
                if self._data.delete_note(project_name, gone):
                    deleted.append(gone)
        for reference in dict.fromkeys(delete_references):
            if self._data.delete_reference(project_name, reference):
                deleted.append(reference)
        if self._data.delete_note(project_name, name):
            deleted.append(name)
        self._plans.delete_activity(project_name, name)
        return ActivityArchived(note=note, deleted=deleted)

    def _learned_document(self, project_name: str) -> str:
        try:
            return self._data.read_context(project_name, LEARNED_DOCUMENT)
        except NotFoundError:
            return ""


def parse_points(learned: str) -> list[LearnedPoint]:
    """One point per line, «Tema: testo» (a bullet is fine); a line without a short theme goes under «Generale»."""
    points = []
    for line in learned.splitlines():
        text = line.strip().lstrip("-*").strip()
        if not text:
            continue
        theme, separator, rest = text.partition(":")
        if separator and rest.strip() and 0 < len(theme.strip()) <= _THEME_CHARS:
            points.append(LearnedPoint(theme=" ".join(theme.split()), text=rest.strip()))
        else:
            points.append(LearnedPoint(theme=GENERAL_THEME, text=text))
    return points


def with_point(document: str, theme: str, line: str) -> str:
    """``line`` as the first point of the ``## <theme>`` section (same theme ignoring case), made at the end when
    missing; a new document gets its header."""
    lines = (document.strip() or LEARNED_HEADER).splitlines()
    wanted = theme.strip().casefold()
    start = next((index for index, text in enumerate(lines) if text.startswith("## ") and text[3:].strip().casefold() == wanted), None)
    if start is None:
        return "\n".join([*lines, "", f"## {theme.strip()}", f"- {line}"]).strip() + "\n"
    return "\n".join([*lines[:start + 1], f"- {line}", *lines[start + 1:]]).strip() + "\n"
