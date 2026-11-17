"""«Elabora WIP»: the new text of a project's WIP note (``wip.md``, after the
last sign) turned into proposals for its activities by **one call** to the
agent ``wip`` of global-agent.yml, with a **structured answer** (``WipAnswer``), then applied
by the app **without LLM** once the user chose them.

1. **Preview** (no LLM): the text the model would get, exactly, masked: the
   date, the open activities (name, title, items not done, numbered), the
   WIP's new text. ``mask{term}`` adds the term to the project's map;
   emails, URLs, IPs and keys are masked only for this call
   (domain/masking/preview.py). Over ``WORD_LIMIT`` words the user may
   process only the first paragraphs.
2. **Process**: the same text, masked again the same way, to the agent
   ``wip`` (its prompt and model from global-agent.yml). The
   proposals come back with their values in clear; one naming an activity or
   an item that is not in the list is dropped. The call is recorded as an
   agent run (origin ``wip``: tokens, cost, latency) and as a ``WipRun``.
3. **Apply** (no LLM): only the chosen proposals, as edited; one on an
   activity or an item that changed meanwhile is skipped. Then the sign goes
   in the note after the processed text, and the ``WipRun`` records what the
   user accepted, corrected, discarded. Or **dismiss**: the user closed the
   proposals without applying any; all of them count as discarded, no sign."""
import json
from datetime import date, datetime, timezone

from core.error import AppError, ConflictError, NotFoundError, UpstreamError, ValidationError
from core.observability import LogPrefix, observed
from domain.agent.outputs import WIP as WIP_OUTPUT, WIP_AGENT
from domain.masking.preview import MaskedText, masked_text, tagged_terms, unmask, without_tags
from domain.project import wip
from models.domain.agent import RunOrigin
from models.domain.masking import MaskCategory, MaskEntry
from models.domain.note import Activity, ActivityStatus, TodoItem, TodoPriority
from models.domain.wip import (
    ProposalKind,
    ProposalPriority,
    WipAnswer,
    WipApplied,
    WipChoice,
    WipPreview,
    WipProposal,
    WipResult,
    WipRun,
    WipState,
)
from service.masking_service import MIN_LENGTH, MaskingService
from service.project_data_service import ProjectDataService
from service.store.wip_store import WipStore
from service.structured_agent_service import StructuredAgentService

_WEEKDAYS = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
_PRIORITIES = {ProposalPriority.HIGH: TodoPriority.HIGH, ProposalPriority.MEDIUM: TodoPriority.MEDIUM, ProposalPriority.LOW: TodoPriority.LOW}


class Listing:
    """The open activities as the model sees them: name → (title, {number: item text}) of the items not done."""

    def __init__(self, activities: list[tuple[str, Activity]]):
        self.items: dict[str, tuple[str, dict[int, str]]] = {
            name: (activity.title, {number: item.text for number, item in enumerate(activity.items, 1) if not item.done})
            for name, activity in activities if activity.status != ActivityStatus.DONE
        }

    def text(self) -> str:
        if not self.items:
            return "(nessuna)"
        lines = []
        for name, (title, items) in self.items.items():
            lines.append(f"- {name} · {title}")
            lines += [f"  {number}. {text}" for number, text in items.items()] or ["  (nessuna voce da fare)"]
        return "\n".join(lines)


class WipService:

    def __init__(self, project_data: ProjectDataService, masking: MaskingService, agents: StructuredAgentService, wip_runs: WipStore):
        self._data = project_data
        self._masking = masking
        self._agents = agents
        self._wip_runs = wip_runs

    # ------------------------------------------------------------------ read
    def state(self, project_name: str) -> WipState:
        """The note (``""`` when it does not exist yet) and the words of its new text."""
        content = self._content(project_name)
        return WipState(content=content, pending_words=wip.words(wip.pending(content)))

    def runs(self, project_name: str) -> list[WipRun]:
        """Newest first."""
        return self._wip_runs.list_runs(project_name)

    # --------------------------------------------------------------- preview
    def preview(self, project_name: str, paragraphs: int | None = None, today: date | None = None) -> WipPreview:
        """The text the model would get, masked, with its aliases. The
        ``mask{term}`` of the text are added to the project's map now.
        ``paragraphs``: how many paragraphs of the new text (None = all)."""
        new = wip.pending(self._content(project_name))
        if not new:
            raise ValidationError("Niente da elaborare: la WIP non ha testo nuovo dopo l'ultimo segno.")
        processed = wip.first_paragraphs(new, paragraphs)
        masked, _ = self._masked(project_name, processed, today or date.today())
        count = len(wip.paragraphs(new))
        return WipPreview(
            text=masked.text, spans=masked.spans, words=wip.words(without_tags(processed)), paragraphs=count,
            processing=len(wip.paragraphs(processed)), over_limit=wip.words(new) > wip.WORD_LIMIT,
        )

    # --------------------------------------------------------------- process
    @observed(LogPrefix.WIP_SERVICE)
    def process(self, project_name: str, paragraphs: int | None = None, today: date | None = None) -> WipResult:
        """One call to the agent ``wip`` on the previewed text; the
        proposals in clear. UpstreamError when the model fails (the run is
        recorded anyway)."""
        today = today or date.today()
        new = wip.pending(self._content(project_name))
        if not new:
            raise ValidationError("Niente da elaborare: la WIP non ha testo nuovo dopo l'ultimo segno.")
        processed = wip.first_paragraphs(new, paragraphs)
        agent = self._agents.agent(WIP_AGENT, WIP_OUTPUT)
        masked, listing = self._masked(project_name, processed, today)
        call = self._agents.call(agent, masked.text)
        entries = self._masking.entries(project_name)
        answer = call.answer if isinstance(call.answer, WipAnswer) else None
        proposals = to_proposals(answer, listing, entries, masked.temporary) if answer else []
        run_id = self._agents.save(call, project_name=project_name, origin=RunOrigin.WIP, input=unmask(masked.text, entries, masked.temporary),
                                   output=json.dumps([proposal.model_dump(mode="json") for proposal in proposals], ensure_ascii=False))
        if call.error is not None:
            raise UpstreamError(f"L'agente {agent.name} non ha risposto: {call.error}")
        self._wip_runs.save_run(WipRun(run_id=run_id, project_name=project_name, model=agent.model,
                                       prompt_version=agent.prompt_version, proposed=len(proposals), processed=processed))
        return WipResult(run_id=run_id, proposals=proposals)

    # ----------------------------------------------------------------- apply
    @observed(LogPrefix.WIP_SERVICE)
    def apply(self, project_name: str, run_id: str, choices: list[WipChoice], now: datetime | None = None) -> WipApplied:
        """The chosen proposals, in order, then the sign after the processed
        text. ValidationError without choices (nothing chosen = nothing
        done, no sign); ConflictError when the run was applied already or
        the WIP's new text no longer starts with what was processed."""
        run = self._open_run(project_name, run_id)
        if not choices:
            raise ValidationError("Nessuna proposta scelta: niente da applicare (la WIP resta da elaborare).")
        now = now or datetime.now()
        signed = wip.with_sign(self._content(project_name), run.processed, now)
        if signed is None:
            raise ConflictError("La WIP è cambiata dopo l'elaborazione: rielaborala.")

        applied, skipped = [], []
        corrected = 0
        for choice in choices:
            try:
                applied.append(self._apply(project_name, choice.proposal))
                corrected += choice.edited
            except (AppError, _Skipped) as exc:
                skipped.append(f"{_label(choice.proposal)}: {exc}")
        self._data.save_note(project_name, wip.WIP_NOTE, signed)
        self._wip_runs.save_run(run.model_copy(update={
            "applied_at": datetime.now(timezone.utc), "accepted": len(applied) - corrected, "corrected": corrected,
            "discarded": max(run.proposed - len(choices), 0), "skipped": len(skipped),
        }))
        return WipApplied(applied=applied, skipped=skipped)

    @observed(LogPrefix.WIP_SERVICE)
    def dismiss(self, project_name: str, run_id: str) -> WipRun:
        """The proposals closed without applying any: all of them discarded,
        no sign (the WIP stays to process). ConflictError when they were
        applied or dismissed already."""
        run = self._open_run(project_name, run_id)
        return self._wip_runs.save_run(run.model_copy(update={"dismissed_at": datetime.now(timezone.utc), "discarded": run.proposed}))

    # --------------------------------------------------------------- helpers
    def _open_run(self, project_name: str, run_id: str) -> WipRun:
        """The run, still waiting for the user's choice."""
        run = self._wip_runs.get_run(run_id)
        if run is None or run.project_name != project_name:
            raise NotFoundError(f"Elaborazione non trovata: {run_id}")
        if run.applied_at is not None:
            raise ConflictError("Queste proposte sono già state applicate.")
        if run.dismissed_at is not None:
            raise ConflictError("Queste proposte sono state annullate: rielabora la WIP.")
        return run

    def _content(self, project_name: str) -> str:
        try:
            return self._data.read_note(project_name, wip.WIP_NOTE)
        except NotFoundError:
            return ""

    def _masked(self, project_name: str, processed: str, today: date) -> tuple[MaskedText, Listing]:
        """The whole input of the call, masked: the ``mask{}`` terms are added to the map first."""
        tagged = tagged_terms(processed)
        short = [term for term in tagged if len(term) < MIN_LENGTH]
        if short:
            raise ValidationError(f"mask{{}} vuole almeno {MIN_LENGTH} caratteri: {', '.join(short)}.")
        for term in tagged:
            self._masking.add_term(project_name, MaskCategory.TERM, term)
        listing = Listing(self._data.activities(project_name))
        return masked_text(model_input(today, listing, processed), self._masking.entries(project_name), tagged), listing

    def _apply(self, project_name: str, proposal: WipProposal) -> str:
        """One proposal; _Skipped (or an AppError) when it cannot be applied anymore."""
        if proposal.kind == ProposalKind.NEW_ACTIVITY:
            title = proposal.title.strip()
            if not title:
                raise _Skipped("manca il titolo")
            items = [TodoItem(text=text.strip()) for text in proposal.items if text.strip()]
            name = self._data.create_activity(project_name, Activity(title=title, description=proposal.description.strip(), items=items))
            return f"Nuova attività «{title}» ({name})"
        activity = self._data.activity(project_name, proposal.activity)
        if proposal.kind == ProposalKind.ADD_ITEM:
            if not proposal.text.strip():
                raise _Skipped("la voce è vuota")
            item = TodoItem(text=proposal.text.strip(), priority=_PRIORITIES.get(proposal.priority) if proposal.priority else None,
                            due=proposal.due)
            self._data.save_activity(project_name, proposal.activity, activity.model_copy(update={"items": [*activity.items, item]}))
            return f"Voce «{item.text}» aggiunta a «{activity.title}»"
        index = proposal.item - 1
        if not 0 <= index < len(activity.items) or activity.items[index].text != proposal.item_text:
            raise _Skipped("la voce è cambiata o non c'è più")
        current = activity.items[index]
        if proposal.kind == ProposalKind.CHECK_ITEM:
            if current.done:
                raise _Skipped("la voce è già fatta")
            changed = current.model_copy(update={"done": True})
            message = f"Spuntata «{current.text}» in «{activity.title}»"
        else:
            update: dict[str, object] = {}
            if proposal.priority:
                update["priority"] = _PRIORITIES[proposal.priority]
            if proposal.due:
                update["due"] = proposal.due
            if not update:
                raise _Skipped("niente da cambiare")
            changed = current.model_copy(update=update)
            message = f"«{current.text}» in «{activity.title}»: " + ", ".join(
                part for part in (f"priorità {proposal.priority.value}" if proposal.priority else "",
                                  f"scadenza {proposal.due.isoformat()}" if proposal.due else "") if part)
        items = [*activity.items[:index], changed, *activity.items[index + 1:]]
        self._data.save_activity(project_name, proposal.activity, activity.model_copy(update={"items": items}))
        return message


def model_input(today: date, listing: Listing, processed: str) -> str:
    """The text the model gets, before masking: today's date, the open activities, the WIP's text without its tags."""
    return (f"Oggi: {today.isoformat()} ({_WEEKDAYS[today.weekday()]})\n\nAttività aperte:\n{listing.text()}\n\n"
            f"Testo nuovo della WIP:\n{without_tags(processed)}")


def to_proposals(answer: WipAnswer, listing: Listing, entries: list[MaskEntry], temporary: dict[str, str]) -> list[WipProposal]:
    """The model's answer as proposals in clear (map and temporary aliases);
    one on an activity or an item not in the list is left out."""
    clear = lambda text: unmask(text, entries, temporary).strip()  # noqa: E731
    proposals: list[WipProposal] = []
    for raw in answer.proposals:
        proposal = WipProposal(
            id=len(proposals) + 1, kind=raw.kind, source=clear(raw.source), activity=raw.activity.strip(), title=clear(raw.title),
            description=clear(raw.description), items=[clear(item) for item in raw.items if item.strip()], text=clear(raw.text),
            item=raw.item, priority=raw.priority, due=raw.due,
        )
        if proposal.kind == ProposalKind.NEW_ACTIVITY:
            if proposal.title:
                proposals.append(proposal)
            continue
        found = listing.items.get(proposal.activity)
        if found is None:
            continue
        proposal.activity_title = found[0]
        if proposal.kind == ProposalKind.ADD_ITEM:
            if proposal.text:
                proposals.append(proposal)
        elif proposal.item in found[1] and (proposal.kind == ProposalKind.CHECK_ITEM or proposal.priority or proposal.due):
            proposal.item_text = found[1][proposal.item]
            proposals.append(proposal)
    return proposals


class _Skipped(Exception):
    """A chosen proposal that cannot be applied anymore: its message says why."""


def _label(proposal: WipProposal) -> str:
    if proposal.kind == ProposalKind.NEW_ACTIVITY:
        return f"Nuova attività «{proposal.title}»"
    if proposal.kind == ProposalKind.ADD_ITEM:
        return f"Voce «{proposal.text}»"
    return f"Voce {proposal.item} di «{proposal.activity_title or proposal.activity}»"
