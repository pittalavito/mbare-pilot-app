"""Request/response models of a project's masking map."""
from pydantic import BaseModel

from models.domain.masking import MaskCategory, MaskEntry


class MaskEntryResponse(BaseModel):
    category: str
    """``repository`` | ``person`` | ``email`` | ``term``."""
    value: str
    alias: str
    manual: bool
    """Added by hand (True) or registered by a tool (False)."""

    @classmethod
    def from_entry(cls, entry: MaskEntry) -> "MaskEntryResponse":
        return cls(**entry.model_dump())


class MaskRequest(BaseModel):
    category: MaskCategory = MaskCategory.TERM
    value: str
