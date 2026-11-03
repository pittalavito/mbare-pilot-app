"""The ``todoMbarePilot{description}`` comments in the code: how they are
found and the reference note they become. Pure functions: no filesystem here.

The marker is found anywhere in a line, whatever the language's comment
syntax (``//``, ``#``, ``/* */``, ``<!-- -->``...): the description is the
text between the braces, on that line only."""
import re
from datetime import datetime

from models.domain.code_todo import CodeTodo
from models.domain.note import Reference

MARKER = "todoMbarePilot"
_PATTERN = re.compile(MARKER + r"\{([^}\n]*)\}")
TITLE = "TODO Mbare Pilot"
"""The scan's reference note: ``code-reference-todo-mbare-pilot.md``."""
SOURCE = MARKER
"""The note's ``Fonte``: what tells it was written by the scan."""


def find(text: str) -> list[CodeTodo]:
    """The comments in ``text``, in order; an empty description is skipped."""
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        found += [CodeTodo(line=number, description=" ".join(match.group(1).split()))
                  for match in _PATTERN.finditer(line) if match.group(1).strip()]
    return found


def reference(todos: dict[str, list[CodeTodo]], when: datetime) -> Reference:
    """The note of a scan: the comments grouped by file (paths relative to the
    project), files in alphabetical order."""
    count = sum(len(items) for items in todos.values())
    stamp = when.strftime("%Y-%m-%d %H:%M")
    if not count:
        content = f"Nessun commento `{MARKER}{{…}}` trovato nel codice (scansione del {stamp})."
    else:
        lines = [f"Commenti `{MARKER}{{…}}` trovati nel codice il {stamp}: {count} in {len(todos)} file."]
        for path in sorted(todos, key=str.lower):
            lines += ["", f"### {path}"] + [f"- riga {todo.line}: {todo.description}" for todo in todos[path]]
        content = "\n".join(lines)
    return Reference(title=TITLE, source=SOURCE, content=content)
