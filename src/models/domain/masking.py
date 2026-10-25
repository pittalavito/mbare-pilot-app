"""Masking: sensitive values of a project (repository names, people, emails,
terms) replaced with stable aliases before text reaches an LLM, and put back
in its answers. One permanent map per project.

A tool declares what is sensitive in its output with the ``Sensitive`` marker
(see ``RepositoryName``, ``PersonName``, ``EmailAddress``): the agent layer
reads the markers (``sensitive_values``) and registers the values, the tool
never does."""
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel


class MaskCategory(StrEnum):
    REPOSITORY = "repository"
    PERSON = "person"
    EMAIL = "email"
    TERM = "term"
    """Anything else, usually added by hand."""

    @property
    def alias_prefix(self) -> str:
        _PREFIXES = {
            MaskCategory.REPOSITORY: "REPO",
            MaskCategory.PERSON: "PERSONA",
            MaskCategory.EMAIL: "EMAIL",
            MaskCategory.TERM: "TERMINE",
        }
        return _PREFIXES[self]


@dataclass(frozen=True)
class Sensitive:
    """Marker in a tool output field's annotation: the field's value (a string,
    or a list of strings) is a sensitive value of ``category``. No effect on
    the model itself: serialization is unchanged."""
    category: MaskCategory


MaskRepositoryName = Annotated[str, Sensitive(MaskCategory.REPOSITORY)]
MaskRepositoryNames = Annotated[list[str], Sensitive(MaskCategory.REPOSITORY)]
MaskPersonName = Annotated[str, Sensitive(MaskCategory.PERSON)]
MaskEmailAddress = Annotated[str, Sensitive(MaskCategory.EMAIL)]


def sensitive_values(value: Any) -> Iterator[tuple[MaskCategory, str]]:
    """Every value marked ``Sensitive`` in a tool's output model, nested models
    and lists included. Unmarked fields are not looked at as values."""
    if isinstance(value, BaseModel):
        for name, info in type(value).model_fields.items():
            field = getattr(value, name)
            marker = next((item for item in info.metadata if isinstance(item, Sensitive)), None)
            if marker is None:
                yield from sensitive_values(field)
            else:
                yield from ((marker.category, text) for text in _texts(field))
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from sensitive_values(item)


def _texts(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        if value:
            yield value
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _texts(item)


class MaskEntry(BaseModel):
    """One masked value of a project."""
    category: MaskCategory
    value: str
    """The real value, as first seen."""
    alias: str
    """What the LLM sees instead, e.g. ``REPO_1``; never reused."""
    manual: bool = False
    """Added by hand (True) or registered by a tool (False)."""
