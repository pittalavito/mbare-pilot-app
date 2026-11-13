"""From an agent's run to an automation (plan 11): the draft the app makes of
what the Operator did, without an LLM, and what the user saves of it."""
from typing import Any

from pydantic import BaseModel, Field

from models.domain.agent import Name
from models.domain.pipeline import AutomationPurpose


class LearnedStep(BaseModel):
    """A successful tool call of the run, with the real values (not the aliases)."""
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    read_only: bool = False
    """Only reads (e.g. git_status): left out unless the user keeps it."""


class LearnedValue(BaseModel):
    """A value of the calls' arguments: fixed, or a field of the automation."""
    value: str
    field: str = ""
    """The proposed field (``branch``, ``base``, ``task``); ``""`` = fixed."""


class LearnDraft(BaseModel):
    run_id: str
    steps: list[LearnedStep]
    values: list[LearnedValue]
    cost_eur: float = 0.0
    """What the run that taught it cost."""


class LearnRequest(BaseModel):
    """What the user saves: the steps kept, in order, and which values are fields."""
    name: Name
    description: str = ""
    purpose: AutomationPurpose = AutomationPurpose.NONE
    steps: list[LearnedStep] = Field(min_length=1)
    fields: dict[str, str] = Field(default_factory=dict)
    """Value → field: every argument equal to the value becomes ``{in:field}``; ``""`` = fixed."""
