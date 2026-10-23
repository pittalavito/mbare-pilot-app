"""Masker: replaces a project's sensitive values with their aliases in a text
(``mask``) and the aliases with the values again (``unmask``). Pure: built
from the project's entries, no Redis here.

Masking is case-insensitive and whole-word (``api`` is not masked inside
``rapid``); longer values win over values they contain. Unmasking replaces
only aliases of this project (``REPO_1``, ``PERSONA_2``, ...)."""
import re

from models.domain.masking import MaskCategory, MaskEntry

_ALIAS = re.compile(r"\b(?:%s)_\d+\b" % "|".join(category.alias_prefix for category in MaskCategory))


class Masker:

    def __init__(self, entries: list[MaskEntry]):
        self._alias_by_value = {entry.value.lower(): entry.alias for entry in entries}
        self._value_by_alias = {entry.alias: entry.value for entry in entries}
        values = sorted(self._alias_by_value, key=len, reverse=True)
        self._pattern = re.compile("|".join(_whole(value) for value in values), re.IGNORECASE) if values else None

    def mask(self, text: str) -> str:
        if not self._pattern or not text:
            return text
        return self._pattern.sub(lambda match: self._alias_by_value[match.group(0).lower()], text)

    def unmask(self, text: str) -> str:
        if not self._value_by_alias or not text:
            return text
        return _ALIAS.sub(lambda match: self._value_by_alias.get(match.group(0), match.group(0)), text)


def _whole(value: str) -> str:
    """``value`` escaped, not glued to letters or digits where it starts/ends with one."""
    start = r"(?<!\w)" if re.match(r"\w", value[0]) else ""
    end = r"(?!\w)" if re.match(r"\w", value[-1]) else ""
    return f"{start}{re.escape(value)}{end}"
