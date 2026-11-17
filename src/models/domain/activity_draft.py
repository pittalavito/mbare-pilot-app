"""«📎 Da riferimenti» (plan 16): a new activity proposed by the secretary from titles."""
from pydantic import BaseModel, Field


class DraftAnswer(BaseModel):
    """The secretary's structured answer."""
    title: str = ""
    description: str = ""
    items: list[str] = Field(default_factory=list)
    """The todo items, in order."""


class ActivityDraft(DraftAnswer):
    """The proposal in clear, for the user to correct before creating the activity."""
    references: list[str] = []
    """The chosen reference notes, to link to the activity."""
    run_id: str
    cost_eur: float = 0.0
