"""«📎 Da riferimenti» (plan 16): **one call** to the agent ``bozza-attivita`` of
global-agent.yml (structured answer ``DraftAnswer``, no tools, few tokens). It reads **only the
titles** of the chosen references (notes of the project, also those just copied
from Jira or Confluence) and of the chosen pieces of the context index, plus
what the user wrote in «Cosa vuoi fare» (plan 34, the main intent; it is enough
alone), masked like «Elabora WIP», and proposes title, description and todo items. Nothing is
created: the user corrects the proposal and creates the activity as usual.
Recorded as an agent run (origin ``draft``)."""
import json

from core.error import UpstreamError, ValidationError
from core.observability import LogPrefix, observed
from domain.agent.outputs import DRAFT, DRAFT_AGENT
from domain.masking.preview import masked_text, unmask
from domain.project.data_paths import note_file_name
from models.domain.activity_draft import ActivityDraft, DraftAnswer
from models.domain.agent import RunOrigin
from service.masking_service import MaskingService
from service.project_data_service import ProjectDataService
from service.structured_agent_service import StructuredAgentService

MAX_TITLES = 30
"""Titles beyond these are ignored (the call stays small)."""
_TITLE_CHARS = 200
MAX_DESCRIPTION_CHARS = 2000
"""«Cosa vuoi fare» beyond these characters is cut."""


class ActivityDraftService:

    def __init__(self, project_data: ProjectDataService, masking: MaskingService, agents: StructuredAgentService):
        self._data = project_data
        self._masking = masking
        self._agents = agents

    @observed(LogPrefix.DRAFT_SERVICE)
    def propose(self, project_name: str, references: list[str], context: list[str], description: str = "") -> ActivityDraft:
        """The proposed activity from ``description`` (what the user wants) and the titles of ``references`` (note names) and ``context`` (titles)."""
        names = list(dict.fromkeys(note_file_name(name) for name in references if name.strip()))
        reference_titles = [self._data.reference(project_name, name)[1].title for name in names]
        context_titles = list(dict.fromkeys(title.strip() for title in context if title.strip()))
        description = description.strip()
        if not reference_titles and not context_titles and not description:
            raise ValidationError("Scrivi cosa vuoi fare o scegli almeno un riferimento o un risultato del contesto.")
        agent = self._agents.agent(DRAFT_AGENT, DRAFT)
        entries = self._masking.entries(project_name)
        masked = masked_text(model_input(reference_titles, context_titles, description), entries)
        call = self._agents.call(agent, masked.text)

        clear = lambda text: unmask(text, entries, masked.temporary).strip()  # noqa: E731
        answer = call.answer if isinstance(call.answer, DraftAnswer) else None
        draft = DraftAnswer(title=clear(answer.title), description=clear(answer.description),
                            items=[text for text in map(clear, answer.items) if text]) if answer else DraftAnswer()
        if answer and not draft.title:
            draft.title = (reference_titles or context_titles or [description.splitlines()[0][:_TITLE_CHARS]])[0]
        run_id = self._agents.save(call, project_name=project_name, origin=RunOrigin.DRAFT, input=unmask(masked.text, entries, masked.temporary),
                                   output=json.dumps(draft.model_dump(mode="json"), ensure_ascii=False))
        if call.error is not None:
            raise UpstreamError(f"L'agente {agent.name} non ha risposto: {call.error}")
        return ActivityDraft(**draft.model_dump(), references=names, run_id=run_id, cost_eur=round(call.telemetry.total_tokens.cost_eur, 6))


def model_input(references: list[str], context: list[str], description: str = "") -> str:
    """The text the secretary gets, before masking: what the user wants, then only titles, at most ``MAX_TITLES``."""
    lines: list[str] = []
    if description.strip():
        lines += ["Cosa voglio fare:", description.strip()[:MAX_DESCRIPTION_CHARS]]
    if references:
        lines.append("Riferimenti:" if not lines else "\nRiferimenti:")
        lines += [f"- {title.strip()[:_TITLE_CHARS]}" for title in references[:MAX_TITLES]]
    if context:
        lines.append("Contesto del progetto:" if not lines else "\nContesto del progetto:")
        lines += [f"- {title[:_TITLE_CHARS]}" for title in context[:MAX_TITLES]]
    return "\n".join(lines)
