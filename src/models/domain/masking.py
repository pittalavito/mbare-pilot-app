"""Masking: sensitive values of a project (repository names, people, emails,
terms) replaced with stable aliases before text reaches an LLM, and put back
in its answers. One permanent map per project."""
from enum import StrEnum

from pydantic import BaseModel


class MaskCategory(StrEnum):
    REPOSITORY = "repository"
    PERSON = "person"
    EMAIL = "email"
    TERM = "term"
    """Anything else, usually added by hand."""

    @property
    def alias_prefix(self) -> str:
        return _PREFIXES[self]


_PREFIXES = {
    MaskCategory.REPOSITORY: "REPO",
    MaskCategory.PERSON: "PERSONA",
    MaskCategory.EMAIL: "EMAIL",
    MaskCategory.TERM: "TERMINE",
}


class MaskEntry(BaseModel):
    """One masked value of a project."""
    category: MaskCategory
    value: str
    """The real value, as first seen."""
    alias: str
    """What the LLM sees instead, e.g. ``REPO_1``; never reused."""
    manual: bool = False
    """Added by hand (True) or registered by a tool (False)."""
