"""Step «Chiudi» of an activity (plan 18).

- **Proposal** (``propose_learned``): **one call** to the agent ``imparato`` of
  global-agent.yml (structured answer ``LearnedAnswer``, no tools): the
  activity's title and description, its tasks and the round's summary,
  masked; a few points to remember, in clear, for the user to correct.
- **Close** (``close``): what was learned goes in the project's context
  document ``context/imparato.md`` **by theme** (plan 27): each point
  («Tema: testo», one per line; no theme = «Generale») at the top of its
  ``## <tema>`` section (made when missing), with the activity and the date;
  the document is then indexed for the agents with ``search_context``. Nothing learned = the
  document is not touched. The activity becomes «done» and its round stops.
- **Reopen** (``reopen``): back to «in progress»; the section already written
  stays (the document is a diary: corrected by hand from the Contesto section)."""
import json
from datetime import date

from core.error import NotFoundError, UpstreamError
from core.observability import LogPrefix, observed
from domain.agent.outputs import LEARNED, LEARNED_AGENT
from domain.masking.preview import masked_text, unmask
from domain.project.data_paths import note_file_name
from models.domain.activity_close import ActivityClosed, LearnedAnswer, LearnedDraft, LearnedPoint
from models.domain.agent import RunOrigin
from models.domain.note import ActivityStatus
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
                 plans: PlanStore, rag: RagService | None = None):
        self._data = project_data
        self._masking = masking
        self._agents = agents
        self._plan = plan
        self._plans = plans
        self._rag = rag

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
