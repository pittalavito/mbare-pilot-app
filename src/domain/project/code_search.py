"""A free search in the code: the query as a pattern, the matches of
one file's text, the glob filter and the code reference a search becomes.
Pure functions: no filesystem here."""
import fnmatch
import re
from datetime import datetime

from core.error import ValidationError
from models.domain.code_search import CodeMatch, CodeQuery
from models.domain.note import Reference

SOURCE = "search"
"""A reference written by a search: saved again with the same title it is rewritten."""
LINE_CHARS = 200
"""How much of a matched line is kept."""


def pattern(query: CodeQuery) -> re.Pattern[str]:
    """The query as a pattern: plain text escaped, a regex as it is (ValidationError when it is broken)."""
    if not query.regex:
        return re.compile(re.escape(query.query))
    try:
        return re.compile(query.query)
    except re.error as exc:
        raise ValidationError(f"Regex non valida: {exc}") from exc


def wanted(path: str, files: str) -> bool:
    """``path`` (relative to its repository) matches the glob; a glob without ``/`` looks at the file name."""
    if not files.strip():
        return True
    glob = files.strip()
    return fnmatch.fnmatch(path, glob) or ("/" not in glob and fnmatch.fnmatch(path.rsplit("/", 1)[-1], glob))


def find(text: str, path: str, found: re.Pattern[str], chars: int = LINE_CHARS) -> list[CodeMatch]:
    """The lines of ``text`` where the pattern is, in order, trimmed and cut to ``chars``."""
    return [CodeMatch(path=path, line=number, text=_cut(line.strip(), chars))
            for number, line in enumerate(text.splitlines(), start=1) if found.search(line)]


def _cut(text: str, chars: int) -> str:
    return text if len(text) <= chars else text[: chars - 1] + "…"


def describe(query: CodeQuery) -> str:
    """The search in one line: what, how and where."""
    parts = [f"«{query.query}»" + (" (regex)" if query.regex else "")]
    if query.files.strip():
        parts.append(f"file {query.files.strip()}")
    if query.repository.strip():
        parts.append(f"repository {query.repository.strip()}")
    return ", ".join(parts)


def reference(title: str, query: CodeQuery, matches: list[CodeMatch], total: int, when: datetime) -> Reference:
    """The code reference of a search: the search used and every match, ``path:line → line``."""
    lines = [f"Ricerca: {describe(query)} · {when:%d/%m/%Y %H:%M}", ""]
    if not matches:
        lines.append("Nessun risultato.")
    lines += [f"- `{match.path}:{match.line}` → {match.text}" for match in matches]
    if total > len(matches):
        lines += ["", f"… e altri {total - len(matches)} risultati: restringi la ricerca."]
    return Reference(title=title, source=SOURCE, source_url=describe(query), repository=query.repository.strip(), content="\n".join(lines))
