"""The board of Mbare Pilot: the app's future changes, from ``board/roadmap.yml`` of
the definitions (the data folder's, written by the UI, or the app's)."""
from enum import StrEnum

from pydantic import BaseModel, Field


class RoadmapStatus(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class RoadmapPriority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RoadmapCard(BaseModel):
    """A card as the UI writes it."""
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    kind: str = ""
    """bug, funzione, refactoring, documentazione, integrazione, uso, progettazione, rag."""
    priority: RoadmapPriority | None = None
    owner: str = ""
    """Who will do it: tu, claude, copilot, agente remoto."""
    status: RoadmapStatus = RoadmapStatus.TODO
    feasibility: str = ""


class RoadmapItem(RoadmapCard):
    id: str = ""
    """Stable, written in the file; one without gets it from its title."""


class Roadmap(BaseModel):
    goal: str = ""
    """The milestone."""
    vision: str = ""
    """What the board is for."""
    items: list[RoadmapItem] = Field(default_factory=list)
