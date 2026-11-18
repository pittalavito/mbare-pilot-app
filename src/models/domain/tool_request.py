"""Requests of tools that do not exist yet (plan 20): written by the Architetto,
worked by Claude Code on the mbare-pilot-app repository through its own MCP server."""
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ToolRequestStatus(StrEnum):
    OPEN = "open"
    WORKING = "working"
    """Claude Code is on it."""
    DONE = "done"
    """Written: ``pr_url`` says where."""
    DISMISSED = "dismissed"
    """Not done: ``reason`` says why."""


class ToolRequest(BaseModel):
    id: int | None = None
    title: str = Field(min_length=1)
    objective: str = ""
    """What the tool must do: its arguments, the text it returns, when it fails."""
    criteria: list[str] = []
    project_name: str = ""
    """Where it was asked (the app's tools serve every project)."""
    automation: str = ""
    """The automation that needs it, by name; ``""`` = none."""
    activity: str = ""
    status: ToolRequestStatus = ToolRequestStatus.OPEN
    pr_url: str = ""
    reason: str = ""
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class ToolRequestDetail(ToolRequest):
    """A request with the automation that needs the tool, for Claude Code."""
    automation_yaml: str = ""
    """The automation as YAML; ``""`` = none (or it is gone)."""
