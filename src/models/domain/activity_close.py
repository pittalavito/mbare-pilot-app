"""Step «Chiudi» of an activity (plan 18): what it taught goes in ``context/imparato.md``."""
from pydantic import BaseModel, Field


class LearnedPoint(BaseModel):
    theme: str = Field(description="Il tema in una o due parole (es. Build, Test, Dominio, Copilot, Convenzioni).")
    text: str = Field(description="La cosa da ricordare, breve.")


class LearnedAnswer(BaseModel):
    """The agent ``imparato``'s structured answer."""
    points: list[LearnedPoint] = Field(default_factory=list, description="Poche cose da ricordare per i lavori futuri, ognuna col suo tema.")


class LearnedDraft(BaseModel):
    """The proposal in clear, for the user to correct before closing."""
    points: list[LearnedPoint] = []
    run_id: str
    cost_eur: float = 0.0


class ActivityClosed(BaseModel):
    activity: str
    context: str | None = None
    """The context document written (``imparato.md``); None when nothing was learned."""
    index_error: str | None = None
    """Why the context index was not updated (the document is saved anyway)."""


class ActivityArchived(BaseModel):
    """«🗄 Archivia» (plan 33): the summary note written and what was deleted."""
    note: str
    deleted: list[str] = []
    """The notes deleted: the activity, its tasks, their answers and drafts, the references chosen."""
