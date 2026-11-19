"""The board of Mbare Pilot (plan 30): the app's future activities, from
``roadmap.yml`` of the definitions (the app's, or the data folder's)."""
from enum import StrEnum

from pydantic import BaseModel, Field


class RoadmapStatus(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class RoadmapItem(BaseModel):
    title: str = Field(min_length=1)
    description: str = ""
    kind: str = ""
    """uso, progettazione, refactoring, documentazione, rag, integrazione."""
    owner: str = ""
    """Who will do it: tu, claude, copilot, agente remoto."""
    status: RoadmapStatus = RoadmapStatus.TODO
    feasibility: str = ""


class Roadmap(BaseModel):
    goal: str = ""
    """The milestone (e.g. «Demo datapizza»)."""
    vision: str = ""
    """What the board will become."""
    items: list[RoadmapItem] = Field(default_factory=list)
