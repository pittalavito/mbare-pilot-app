"""Request/response models of «Elabora WIP» (/projects/{project}/wip)."""
from pydantic import BaseModel, Field

from models.domain.wip import WipChoice


class WipParagraphsRequest(BaseModel):
    paragraphs: int | None = Field(None, ge=1)
    """How many paragraphs of the new text to process; None = all."""


class WipRunRequest(BaseModel):
    run_id: str


class WipApplyRequest(BaseModel):
    run_id: str
    choices: list[WipChoice]
    """The proposals chosen, as edited; at least one."""
