"""«📌 Oggi» (service/today_service.py): what needs the user in a project,
computed without LLM, for the panel of the Attività tab and the secretary's
tool ``today``."""
from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field


class WaitingKind(StrEnum):
    TASK = "task"
    """An agent task created, in refinement or to verify."""
    COPILOT = "copilot"
    """A Copilot session waiting for the user's answer."""


class TodayWaiting(BaseModel):
    kind: WaitingKind
    task: str = Field(description="The agent task's note name.")
    title: str
    status: str = Field(description="The task's status (created, refinement, to_verify) or why Copilot waits (answer, question).")
    session_id: int | None = Field(None, description="The Copilot session, for kind copilot.")


class TodayItem(BaseModel):
    """An item not done with a due date."""
    activity: str = Field(description="The activity's note name.")
    activity_title: str
    item: int = Field(description="Its number in the activity's todo list (1-based).")
    text: str
    due: date


class TodayActivity(BaseModel):
    """An activity whose items are all done, not done itself."""
    activity: str
    title: str
    items: int


class Today(BaseModel):
    date: date
    due_soon_days: int
    waiting: list[TodayWaiting]
    overdue: list[TodayItem]
    """The oldest due date first."""
    due_soon: list[TodayItem]
    """Due within ``due_soon_days`` days (today included), the nearest first."""
    to_close: list[TodayActivity]
