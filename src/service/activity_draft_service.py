"""«📎 Da riferimenti» (plan 16): **one call** to the secretary's model with a
structured answer (``DraftAnswer``), no tools, few tokens. It reads **only the
titles** of the chosen references (notes of the project, also those just copied
from Jira or Confluence) and of the chosen pieces of the context index, masked
like «Elabora WIP», and proposes title, description and todo items. Nothing is
created: the user corrects the proposal and creates the activity as usual.
Recorded as an agent run (origin ``draft``)."""
import json
from time import perf_counter
from uuid import uuid4

from datapizza.tracing import ContextTracing

from core.error import UpstreamError, ValidationError
from core.observability import LogPrefix, log_exception, observed
from domain.agent.tracing import Adapter as TracingAdapter
from domain.chat.chatbots_default import DEFAULT_DRAFT_PROMPT
from domain.masking.preview import masked_text, unmask
from domain.project.data_paths import note_file_name
from models.domain.activity_draft import ActivityDraft, DraftAnswer
from models.domain.agent import AgentRunRecord, RunOrigin
from models.domain.chat import split_model_key
from models.domain.chatbot import Chatbot, ChatbotKind
from service.chat_service import ChatService
from service.masking_service import MaskingService
from service.model_service import require_usable_model
from service.project_data_service import ProjectDataService
from service.store.catalog_store import CatalogStore
from service.store.chatbot_store import ChatbotStore
from service.store.run_store import RunStore

MAX_TITLES = 30
"""Titles beyond these are ignored (the call stays small)."""
_TITLE_CHARS = 200


class ActivityDraftService:

    def __init__(self, project_data: ProjectDataService, masking: MaskingService, chatbots: ChatbotStore, chat: ChatService,
                 catalog: CatalogStore, runs: RunStore):
        self._data = project_data
        self._masking = masking
        self._chatbots = chatbots
        self._chat = chat
        self._catalog = catalog
        self._runs = runs

    @observed(LogPrefix.DRAFT_SERVICE)
    def propose(self, project_name: str, references: list[str], context: list[str]) -> ActivityDraft:
        """The proposed activity from the titles of ``references`` (note names) and ``context`` (titles)."""
        names = list(dict.fromkeys(note_file_name(name) for name in references if name.strip()))
        reference_titles = [self._data.reference(project_name, name)[1].title for name in names]
        context_titles = list(dict.fromkeys(title.strip() for title in context if title.strip()))
        if not reference_titles and not context_titles:
            raise ValidationError("Scegli almeno un riferimento o un risultato del contesto.")
        entries = self._masking.entries(project_name)
        masked = masked_text(model_input(reference_titles, context_titles), entries)
        secretary = self._secretary(project_name)
        require_usable_model(self._catalog, secretary.model)
        client = self._chat.get_client(secretary.model)

        answer, error = None, None
        start = perf_counter()
        with ContextTracing().trace(f"draft.{secretary.name}") as current_trace:
            try:
                response = client.structured_response(input=masked.text, output_cls=DraftAnswer, system_prompt=DEFAULT_DRAFT_PROMPT)
                if not response.structured_data:
                    raise ValueError("nessuna risposta strutturata")
                data = response.structured_data[0]
                answer = DraftAnswer.model_validate(data.model_dump() if hasattr(data, "model_dump") else data)
            except Exception as exc:  # noqa: BLE001 - any failure of the call is recorded and reported
                log_exception(LogPrefix.DRAFT_SERVICE, "Proposta attività fallita (%s)", project_name)
                error = str(exc) or type(exc).__name__
            telemetry = TracingAdapter.to_run_telemetry(current_trace.get_spans(), self._catalog.price_list())
        latency_ms = round((perf_counter() - start) * 1000, 1)

        clear = lambda text: unmask(text, entries, masked.temporary).strip()  # noqa: E731
        draft = DraftAnswer(title=clear(answer.title), description=clear(answer.description),
                            items=[text for text in map(clear, answer.items) if text]) if answer else DraftAnswer()
        if answer and not draft.title:
            draft.title = reference_titles[0] if reference_titles else context_titles[0]
        run_id = str(uuid4())
        self._runs.save(AgentRunRecord(
            run_id=run_id, project_name=project_name, origin=RunOrigin.DRAFT, config_name=f"draft/{secretary.name}", role_name="draft",
            prompt_id=0, prompt_version=0, model=split_model_key(secretary.model)[1], ok=error is None, error=error,
            latency_ms=latency_ms, input=unmask(masked.text, entries, masked.temporary),
            output=json.dumps(draft.model_dump(mode="json"), ensure_ascii=False), telemetry=telemetry,
        ))
        if error is not None:
            raise UpstreamError(f"Il Segretario non ha risposto: {error}")
        return ActivityDraft(**draft.model_dump(), references=names, run_id=run_id, cost_eur=round(telemetry.total_tokens.cost_eur, 6))

    def _secretary(self, project_name: str) -> Chatbot:
        secretary = next((bot for bot in self._chatbots.list_chatbots(project_name) if bot.kind is ChatbotKind.SECRETARY), None)
        if secretary is None:
            raise ValidationError("Nessun segretario nel progetto: aggiungilo in global-chat-bots.yml (si crea all'avvio o con «Sincronizza da file»).")
        return secretary


def model_input(references: list[str], context: list[str]) -> str:
    """The text the secretary gets, before masking: only titles, at most ``MAX_TITLES``."""
    lines: list[str] = []
    if references:
        lines.append("Riferimenti:")
        lines += [f"- {title.strip()[:_TITLE_CHARS]}" for title in references[:MAX_TITLES]]
    if context:
        lines.append("Contesto del progetto:" if not lines else "\nContesto del progetto:")
        lines += [f"- {title[:_TITLE_CHARS]}" for title in context[:MAX_TITLES]]
    return "\n".join(lines)
