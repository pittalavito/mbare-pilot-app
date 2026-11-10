"""«Elabora WIP»: the WIP note's new text turned into proposals by one call
to the secretary's model with a structured answer (``WipAnswer``), then
applied by the app without LLM (domain/project/wip.py, service/wip_service.py).

The model may only propose: a new activity, an item to add to an existing
activity, an item to tick, a priority or a due date for an item. Each
proposal quotes the sentence of the WIP it comes from."""
from datetime import date, datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field

from models.domain.masking import MaskSpan


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProposalKind(StrEnum):
    NEW_ACTIVITY = "new_activity"
    ADD_ITEM = "add_item"
    CHECK_ITEM = "check_item"
    SET_ITEM = "set_item"
    """Priority or due date of an existing item."""


class ProposalPriority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ------------------------------------------------------- what the model writes

class WipAnswerProposal(BaseModel):
    """One proposal, flat (a small model fills it more reliably than nested types)."""
    kind: ProposalKind = Field(description=(
        "new_activity: a new activity (title, description, items). add_item: an item for an existing activity (activity, "
        "text, priority and due optional). check_item: an existing item is done (activity, item). set_item: priority "
        "and/or due date of an existing item (activity, item, priority, due)."
    ))
    source: str = Field(description="The sentence of the WIP text this proposal comes from, copied as it is.")
    activity: str = Field("", description="add_item, check_item, set_item: the activity's name (attivita-....md) from the list.")
    title: str = Field("", description="new_activity: a short title.")
    description: str = Field("", description="new_activity: one or two sentences.")
    items: list[str] = Field(default_factory=list, description="new_activity: its first items, short.")
    text: str = Field("", description="add_item: the item's text, short.")
    item: int = Field(0, description="check_item, set_item: the item's number in the list.")
    priority: ProposalPriority | None = Field(None, description="add_item, set_item: high, medium or low; null = none.")
    due: date | None = Field(None, description="add_item, set_item: YYYY-MM-DD, relative dates computed from today; null = none.")


class WipAnswer(BaseModel):
    proposals: list[WipAnswerProposal] = Field(description="What to do, in the order of the text; [] = nothing to do.")


# --------------------------------------------------------- what the app shows

class WipProposal(BaseModel):
    """A proposal as the user sees and edits it (values in clear). ``item_text``
    is the item as it was when proposed (from the list sent to the model):
    applying skips the proposal when the item changed meanwhile."""
    id: int
    kind: ProposalKind
    source: str
    activity: str = ""
    activity_title: str = ""
    title: str = ""
    description: str = ""
    items: list[str] = Field(default_factory=list)
    text: str = ""
    item: int = 0
    item_text: str = ""
    priority: ProposalPriority | None = None
    due: date | None = None


class WipPreview(BaseModel):
    """What the model would get, exactly: the masked text with its aliases."""
    text: str
    spans: list[MaskSpan]
    words: int
    """Of the WIP text being processed (not of the list of activities)."""
    paragraphs: int
    """Of the whole new text."""
    processing: int
    """How many of them are being processed."""
    over_limit: bool
    """The new text is over WORD_LIMIT words: the preview offers to process fewer paragraphs."""


class WipState(BaseModel):
    content: str
    """The whole note (``""`` when it does not exist yet)."""
    pending_words: int
    """Of the new text (after the last sign)."""


class WipRun(BaseModel):
    """One «Elabora WIP»: the call and, once applied, what the user did with
    its proposals (for the metrics). The call itself (tokens, cost, latency)
    is an agent run (origin ``wip``) with the same ``run_id``."""
    id: int | None = None
    run_id: str
    project_name: str
    model: str
    prompt_version: int
    proposed: int
    processed: str = ""
    """The WIP text that was processed (paragraphs of the new text), to place the sign."""
    applied_at: datetime | None = None
    accepted: int = 0
    """Applied as proposed."""
    corrected: int = 0
    """Applied after the user changed them."""
    discarded: int = 0
    skipped: int = 0
    """Chosen but not applied: the activity or the item changed meanwhile."""
    created_at: datetime = Field(default_factory=_utc_now)


class WipResult(BaseModel):
    run_id: str
    proposals: list[WipProposal]


class WipChoice(BaseModel):
    """A proposal the user chose, maybe edited (``edited``)."""
    proposal: WipProposal
    edited: bool = False


class WipApplied(BaseModel):
    applied: list[str]
    """What was done, one line each."""
    skipped: list[str]
    """What was not, and why."""
