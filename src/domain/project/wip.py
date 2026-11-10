"""The WIP note (``wip.md``, one per project): free text written by the user,
turned into activities and items by «Elabora WIP». Pure helpers here.

**The sign**: when proposals are applied the app writes a line
``—— elaborato il 05/11 14:30 ——`` after the text it processed. The next time
only the text after the last sign is new; what is above stays as a diary.

**Paragraphs**: the new text split on blank lines. Above ``WORD_LIMIT`` words
the user chooses how many paragraphs to process: the sign goes after them and
the rest stays new."""
import re
from datetime import datetime

WIP_NOTE = "wip.md"
WORD_LIMIT = 2000
"""Above this many words of new text the preview warns and offers to process fewer paragraphs."""

_SIGN = re.compile(r"^—— elaborato il [^\n]* ——[ \t]*$", re.MULTILINE)
_BLANK = re.compile(r"\n[ \t]*\n+")


def sign(when: datetime) -> str:
    return f"—— elaborato il {when:%d/%m %H:%M} ——"


def pending(content: str) -> str:
    """The text after the last sign (all of it when there is none), trimmed."""
    return content[_last_sign_end(content):].strip()


def paragraphs(text: str) -> list[str]:
    """``text`` split on blank lines, empty ones left out."""
    return [part.strip() for part in _BLANK.split(text.strip()) if part.strip()]


def words(text: str) -> int:
    return len(text.split())


def first_paragraphs(text: str, count: int | None) -> str:
    """The first ``count`` paragraphs of ``text`` (None or more than there are = all), joined by a blank line."""
    parts = paragraphs(text)
    return "\n\n".join(parts if count is None else parts[:max(count, 1)])


def with_sign(content: str, processed: str, when: datetime) -> str | None:
    """``content`` with the sign after ``processed`` (paragraphs of the new
    text, as ``first_paragraphs`` gave them); None when the new text no longer
    starts with them (the note changed meanwhile)."""
    new = pending(content)
    done = paragraphs(processed)
    if paragraphs(new)[:len(done)] != done or not done:
        return None
    rest = paragraphs(new)[len(done):]
    diary = content[:_last_sign_end(content)]  # kept as written; the new text is rewritten paragraph by paragraph
    parts = [diary.rstrip(), "\n\n".join(done), sign(when)]
    text = "\n\n".join(part for part in parts if part)
    return text + ("\n\n" + "\n\n".join(rest) if rest else "") + "\n"


def _last_sign_end(content: str) -> int:
    """Where the last sign ends; 0 when there is none."""
    ends = [match.end() for match in _SIGN.finditer(content)]
    return ends[-1] if ends else 0
