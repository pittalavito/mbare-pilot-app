"""The ``todoMbarePilot{description}`` comments found in a project's code
(service/code_todo_service.py) and what a scan wrote."""
from pydantic import BaseModel


class CodeTodo(BaseModel):
    """One comment: its line (from 1) and the text between the braces."""
    line: int
    description: str


class MalformedTodo(BaseModel):
    """A comment that looks like the marker but is not collected: what is wrong."""
    line: int
    problem: str
    """In Italian, what to fix (e.g. «niente spazio prima della {»)."""
    text: str
    """The line, trimmed and cut: where it is."""


class CodeTodoScan(BaseModel):
    """What a scan did. Counts only: the comments stay in the note."""
    note: str | None
    """The reference note written (``code-reference-todo-mbare-pilot.md``);
    None when nothing was found and there was no note to empty."""
    created: bool
    """The note is new (False: rewritten, or none)."""
    files: int
    comments: int
    malformed: int = 0
    """Comments that look like the marker but are written wrong: listed in the note, to fix."""
