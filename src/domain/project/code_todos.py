"""The ``todoMbarePilot{description}`` comments in the code: how they are
found and the reference note they become. Pure functions: no filesystem here.

The marker is found anywhere in a line, whatever the language's comment
syntax (``//``, ``#``, ``/* */``, ``<!-- -->``...): the description is the
text between the braces, on that line only. A comment that looks like the
marker but is written wrong (other case, a space before the brace, no closing
brace on the line, nothing inside) is not collected: ``find_malformed`` says
what is wrong, and the note lists it, so it does not get lost."""
import re
from datetime import datetime

from models.domain.code_todo import CodeTodo, MalformedTodo
from models.domain.note import Reference

MARKER = "todoMbarePilot"
_PATTERN = re.compile(MARKER + r"\{([^}\n]*)\}")
TITLE = "TODO Mbare Pilot"
"""The scan's reference note: ``code-reference-todo-mbare-pilot.md``."""
SOURCE = MARKER
"""The note's ``Fonte``: what tells it was written by the scan."""
EXAMPLE = f"// {MARKER}{{descrizione}}"
_LOOKALIKE = re.compile(r"todo\s*mbare\s*pilot", re.IGNORECASE)
_TEXT_LENGTH = 120


def find(text: str) -> list[CodeTodo]:
    """The comments in ``text``, in order; an empty description is skipped."""
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        found += [CodeTodo(line=number, description=" ".join(match.group(1).split()))
                  for match in _PATTERN.finditer(line) if match.group(1).strip()]
    return found


_COMMENT_TOKENS = re.compile(r"(//|/\*|\*/|<!--|-->|--|#|;|\*|\s)+")


def strip(text: str) -> tuple[str, int, list[int]]:
    """``text`` without the lines that are only a ``todoMbarePilot{...}``
    comment (whatever the comment syntax). Returns the new text, how many lines
    went and the numbers of the lines that also hold code (left as they are)."""
    kept, removed, mixed = [], 0, []
    for number, line in enumerate(text.splitlines(keepends=True), start=1):
        if not _PATTERN.search(line):
            kept.append(line)
        elif _COMMENT_TOKENS.fullmatch(_PATTERN.sub("", line)) or not _PATTERN.sub("", line).strip():
            removed += 1
        else:
            kept.append(line)
            mixed.append(number)
    return "".join(kept), removed, mixed


def find_malformed(text: str) -> list[MalformedTodo]:
    """What looks like the marker in ``text`` but is not collected by ``find``, in order."""
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        for match in _LOOKALIKE.finditer(line):
            exact = _PATTERN.match(line, match.start())
            if exact and exact.group(1).strip():
                continue  # a good one
            found.append(MalformedTodo(line=number, problem=_problem(match.group(0), line[match.end():]), text=_cut(line)))
    return found


def _problem(word: str, rest: str) -> str:
    if word != MARKER:
        return f"si scrive {MARKER} (maiuscole comprese), non {word}"
    if rest.startswith("{"):
        return "la } va chiusa sulla stessa riga" if "}" not in rest else "la descrizione tra le graffe è vuota"
    if rest.lstrip().startswith("{"):
        return "niente spazio tra todoMbarePilot e la {"
    return f"manca {{descrizione}} subito dopo: {EXAMPLE}"


def _cut(line: str) -> str:
    line = " ".join(line.split()).replace("`", "'")
    return line if len(line) <= _TEXT_LENGTH else line[:_TEXT_LENGTH - 1] + "…"


def reference(todos: dict[str, list[CodeTodo]], when: datetime, malformed: dict[str, list[MalformedTodo]] | None = None) -> Reference:
    """The note of a scan: the comments grouped by file (paths relative to the
    project), files in alphabetical order; then the ones to fix, if any."""
    malformed = malformed or {}
    count = sum(len(items) for items in todos.values())
    wrong = sum(len(items) for items in malformed.values())
    stamp = when.strftime("%Y-%m-%d %H:%M")
    if not count:
        lines = [f"Nessun commento `{MARKER}{{…}}` trovato nel codice (scansione del {stamp})."]
    else:
        lines = [f"Commenti `{MARKER}{{…}}` trovati nel codice il {stamp}: {count} in {len(todos)} file."]
        for path in sorted(todos, key=str.lower):
            lines += ["", f"### {path}"] + [f"- riga {todo.line}: {todo.description}" for todo in todos[path]]
    if wrong:
        lines += ["", f"### ⚠️ Da correggere ({wrong}): non raccolti", f"Il formato giusto è `{EXAMPLE}`, su una riga."]
        for path in sorted(malformed, key=str.lower):
            lines += [f"- {path} riga {item.line}: {item.problem} — `{item.text}`" for item in malformed[path]]
    return Reference(title=TITLE, source=SOURCE, content="\n".join(lines))
