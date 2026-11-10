"""Masking of free text written by the user (the WIP note), shown before it is
sent: pure, no Redis here.

Three sources, in this order when they overlap (the longer match wins among
those starting at the same place):

1. **the project's map** (``MaskEntry``: repositories, persons, terms added
   by hand), the same aliases every agent of the project sees;
2. **``mask{term}``** in the text: the term is added to the map by the
   service before masking (so it stays hidden next time and for the other
   agents); here its alias is marked as coming from the tag, and the text
   the model gets has the term's alias without ``mask{}`` around it;
3. **automatic recognition** of what has a recognizable shape (emails,
   URLs, IP addresses, tokens and keys): masked **only for this text**, with
   aliases of their own (``MAIL_1``, ``URL_1``, ``IP_1``, ``CHIAVE_1``) that
   never enter the map.

``masked_text`` returns the text as the model will get it with the position
of every alias (for the preview), and the temporary aliases to unmask the
answer (``unmask``)."""
import re
from dataclasses import dataclass, field

from domain.masking.masker import Masker, whole_word
from models.domain.masking import MaskEntry, MaskOrigin, MaskSpan

MASK_TAG = re.compile(r"mask\{([^{}\n]*)\}")
"""``mask{Acme Spa}``: a term to mask, on one line."""

_AUTO: list[tuple[str, re.Pattern[str]]] = [
    ("MAIL", re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("URL", re.compile(r"\b(?:https?://|www\.)[^\s<>()\"']+[^\s<>()\"'.,;:!?]")),
    ("CHIAVE", re.compile(
        r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{16,}|xox[abpr]-[A-Za-z0-9-]{10,}"
        r"|AKIA[0-9A-Z]{16}|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})"
    )),
    ("IP", re.compile(r"(?<![\w.])(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?![\w.]*\d)")),
]
"""Shapes recognized automatically, with the prefix of their temporary aliases."""
_SECRET_ASSIGNMENT = re.compile(r"(?i)\b(?:password|passwd|pwd|secret|token|api[_-]?key)\s*[=:]\s*(\S+)")
"""``password=…``: only the value is masked."""
_LONG_SECRET = re.compile(r"(?<![\w/+=-])(?=[A-Za-z0-9+/=_-]*\d)(?=[A-Za-z0-9+/=_-]*[A-Za-z])[A-Za-z0-9+/=_-]{32,}(?![\w/+=-])")
"""A long string of letters and digits (base64, hex): likely a key."""


@dataclass
class MaskedText:
    text: str
    """What the model gets."""
    spans: list[MaskSpan] = field(default_factory=list)
    temporary: dict[str, str] = field(default_factory=dict)
    """The automatic aliases and their values, to unmask the answer."""


def tagged_terms(text: str) -> list[str]:
    """The ``mask{term}`` of the text, each once, in order; blank ones left out."""
    return list(dict.fromkeys(term.strip() for term in MASK_TAG.findall(text) if term.strip()))


def without_tags(text: str) -> str:
    """``mask{Acme}`` → ``Acme``: the text with the tags removed, terms kept."""
    return MASK_TAG.sub(lambda match: match.group(1).strip(), text)


def masked_text(text: str, entries: list[MaskEntry], tagged: list[str] | None = None) -> MaskedText:
    """``text`` (tags already removed) masked with the map ``entries`` and the
    automatic recognition. ``tagged``: the terms written as ``mask{}`` (their
    aliases are marked as coming from the tag)."""
    tagged_lower = {term.lower() for term in tagged or []}
    candidates: list[tuple[int, int, int, str, str]] = []  # start, end, priority, value, origin-or-prefix
    alias_by_value = {entry.value.lower(): entry.alias for entry in entries}
    if alias_by_value:
        pattern = re.compile("|".join(whole_word(value) for value in sorted(alias_by_value, key=len, reverse=True)), re.IGNORECASE)
        for match in pattern.finditer(text):
            origin = MaskOrigin.TAG if match.group(0).lower() in tagged_lower else MaskOrigin.MAP
            candidates.append((match.start(), match.end(), 0, match.group(0), origin.value))
    for prefix, pattern in _AUTO:
        candidates += [(match.start(), match.end(), 1, match.group(0), prefix) for match in pattern.finditer(text)]
    candidates += [(match.start(1), match.end(1), 1, match.group(1), "CHIAVE") for match in _SECRET_ASSIGNMENT.finditer(text)]
    candidates += [(match.start(), match.end(), 2, match.group(0), "CHIAVE") for match in _LONG_SECRET.finditer(text)]

    chosen, last_end = [], 0
    for start, end, _, value, source in sorted(candidates, key=lambda item: (item[0], item[2], -(item[1] - item[0]))):
        if start >= last_end:
            chosen.append((start, end, value, source))
            last_end = end

    result = MaskedText(text="")
    automatic: dict[str, str] = {}  # lowercase value → alias
    counters: dict[str, int] = {}
    parts, position, cursor = [], 0, 0
    for start, end, value, source in chosen:
        if source in (MaskOrigin.MAP.value, MaskOrigin.TAG.value):
            alias, origin = alias_by_value[value.lower()], MaskOrigin(source)
        else:
            if value.lower() not in automatic:
                counters[source] = counters.get(source, 0) + 1
                automatic[value.lower()] = f"{source}_{counters[source]}"
                result.temporary[automatic[value.lower()]] = value
            alias = automatic[value.lower()]
            origin = MaskOrigin.AUTO
        parts.append(text[cursor:start])
        position += start - cursor
        result.spans.append(MaskSpan(start=position, end=position + len(alias), alias=alias, origin=origin))
        parts.append(alias)
        position += len(alias)
        cursor = end
    parts.append(text[cursor:])
    result.text = "".join(parts)
    return result


_TEMPORARY = re.compile(r"\b(?:MAIL|URL|IP|CHIAVE)_\d+\b")


def unmask(text: str, entries: list[MaskEntry], temporary: dict[str, str]) -> str:
    """The model's answer with every alias back to its value: the map's and the temporary ones."""
    text = Masker(entries).unmask(text)
    return _TEMPORARY.sub(lambda match: temporary.get(match.group(0), match.group(0)), text) if temporary else text
