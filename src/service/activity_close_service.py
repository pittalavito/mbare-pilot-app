"""Step «Chiudi» of an activity (plan 18).

- **Proposal** (``propose_learned``): **one call** to the agent ``imparato`` of
  global-agent.yml (structured answer ``LearnedAnswer``, no tools): the
  activity's title and description, its tasks and the round's summary,
  masked; a few points to remember, in clear, for the user to correct.
- **Close** (``close``): what was learned goes **at the top** of the project's
  context document ``context/imparato.md`` (one section per activity,
  ``## <title> · <date>`` and its points; no link to the activity, which can
  be deleted), which is then indexed for the Pianificatore, the Refiner,
  Copilot and the chatbots with ``search_context``. Nothing learned = the
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
from models.domain.activity_close import ActivityClosed, LearnedAnswer, LearnedDraft
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
LEARNED_HEADER = "# Imparato\n\nQuello che le attività del progetto hanno insegnato, le più recenti in cima."


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
        points = [text for text in (unmask(point, entries, masked.temporary).strip() for point in answer.points) if text] if answer else []
        run_id = self._agents.save(call, project_name=project_name, origin=RunOrigin.LEARNED, input=unmask(masked.text, entries, masked.temporary),
                                   output=json.dumps(points, ensure_ascii=False))
        if call.error is not None:
            raise UpstreamError(f"L'agente {agent.name} non ha risposto: {call.error}")
        return LearnedDraft(points=points, run_id=run_id, cost_eur=round(call.telemetry.total_tokens.cost_eur, 6))

    @observed(LogPrefix.CLOSE_SERVICE)
    def close(self, project_name: str, activity_name: str, learned: str, today: date | None = None) -> ActivityClosed:
        """What was learned at the top of context/imparato.md (when there is something), then the activity done and its round stopped."""
        name = note_file_name(activity_name)
        activity = self._data.activity(project_name, name)
        points = [line.strip().lstrip("-*").strip() for line in learned.splitlines()]
        points = [point for point in points if point]
        written, index_error = None, None
        if points:
            when = (today or date.today()).strftime("%d/%m/%Y")
            section = f"## {activity.title} · {when}\n" + "\n".join(f"- {point}" for point in points)
            self._data.save_context(project_name, LEARNED_DOCUMENT, with_section(self._learned_document(project_name), section))
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


def with_section(document: str, section: str) -> str:
    """``section`` before the first section of ``document`` (the newest at the top); a new document gets its header."""
    text = document.strip() or LEARNED_HEADER
    head, separator, rest = text.partition("\n## ")
    return f"{head.rstrip()}\n\n{section}\n" + (f"\n## {rest.strip()}\n" if separator else "")
