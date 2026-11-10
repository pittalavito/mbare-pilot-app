"""Markdown split into pieces for the context index: one piece per ``##``
section, a section longer than ``max_words`` split on its paragraphs (a single
paragraph longer than that on its sentences, then words). Pieces are
datapizza ``Chunk`` objects; their metadata say the document's title and the
section, which the search gives back to cite where a piece comes from."""
import re
import uuid

from datapizza.type.type import Chunk

MAX_WORDS = 300
_HEADING = re.compile(r"^##\s+(.+?)\s*#*\s*$")
_PARAGRAPHS = re.compile(r"\n[ \t]*\n+")
_SENTENCES = re.compile(r"(?<=[.!?])\s+")


def title_of(text: str, fallback: str) -> str:
    """The ``# title`` of the document; ``fallback`` without one."""
    return next((line[2:].strip() for line in text.splitlines() if line.startswith("# ") and line[2:].strip()), fallback)


def split_markdown(text: str, title: str, max_words: int = MAX_WORDS) -> list[Chunk]:
    """The pieces of ``text``, in order: metadata ``title``, ``section``,
    ``position``. Empty sections give no piece; the ``# title`` line is not
    part of any piece (it is in every piece's metadata)."""
    sections: list[tuple[str, list[str]]] = [("", [])]
    for line in text.splitlines():
        heading = _HEADING.match(line)
        if heading:
            sections.append((heading.group(1).strip(), []))
        elif not (line.startswith("# ") and not sections[-1][1] and len(sections) == 1):
            sections[-1][1].append(line)
    pieces: list[Chunk] = []
    for section, lines in sections:
        for part in _bounded("\n".join(lines).strip(), max_words):
            pieces.append(Chunk(id=str(uuid.uuid4()), text=part,
                                metadata={"title": title, "section": section, "position": len(pieces)}))
    return pieces


def _bounded(text: str, max_words: int) -> list[str]:
    """``text`` as parts of at most ``max_words`` words, paragraphs kept whole when they fit."""
    if not text:
        return []
    if len(text.split()) <= max_words:
        return [text]
    parts: list[str] = []
    current: list[str] = []
    for unit in _units(text, max_words):
        if current and len(" ".join(current).split()) + len(unit.split()) > max_words:
            parts.append("\n\n".join(current))
            current = []
        current.append(unit)
    if current:
        parts.append("\n\n".join(current))
    return parts


def _units(text: str, max_words: int) -> list[str]:
    """Paragraphs; one too long split on its sentences, a sentence too long on its words."""
    units: list[str] = []
    for paragraph in (part.strip() for part in _PARAGRAPHS.split(text) if part.strip()):
        if len(paragraph.split()) <= max_words:
            units.append(paragraph)
            continue
        for sentence in _SENTENCES.split(paragraph):
            words = sentence.split()
            units += [" ".join(words[start:start + max_words]) for start in range(0, len(words), max_words)]
    return units
