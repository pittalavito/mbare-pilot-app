"""The types of a project's notes. On disk every note is a markdown file of
``notes/``; the type is in its name (``agent-task-<title>.md``,
``todo-list-<title>.md``, ``code-reference-<title>.md``,
``context-reference-<title>.md``, anything else is generic) and the typed ones
follow a template (domain/project/note_templates.py), shown by the app as a form.

References (code, context) are linked to agent tasks and todo lists by name
(their ``references``, many to many): they show only inside what links them."""
from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field


class NoteType(StrEnum):
    GENERIC = "generic"
    """Free markdown."""
    AGENT_TASK = "agent_task"
    """A task for an agent: objective, context, acceptance criteria, constraints."""
    TODO_LIST = "todo_list"
    """A checklist with optional priority and due date per item."""
    CODE_REFERENCE = "code_reference"
    """A piece of code that matters for a task: repository, file, lines, why."""
    CONTEXT_REFERENCE = "context_reference"
    """Context for a task: text copied by hand or from Jira, Confluence, Dynatrace..."""

    @property
    def is_reference(self) -> bool:
        return self in (NoteType.CODE_REFERENCE, NoteType.CONTEXT_REFERENCE)


class TaskStatus(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class ChecklistItem(BaseModel):
    text: str
    done: bool = False


class AgentTask(BaseModel):
    title: str = Field(min_length=1)
    status: TaskStatus = TaskStatus.TODO
    objective: str = ""
    context: str = ""
    criteria: list[ChecklistItem] = []
    """Acceptance criteria."""
    constraints: str = ""
    references: list[str] = []
    """The linked reference notes, by name (``code-reference-<title>.md``...)."""


class TodoPriority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TodoItem(ChecklistItem):
    priority: TodoPriority | None = None
    due: date | None = None


class TodoList(BaseModel):
    title: str = Field(min_length=1)
    items: list[TodoItem] = []
    references: list[str] = []
    """The linked reference notes, by name."""


class Reference(BaseModel):
    """A code or context reference. ``source``: where it was copied from
    (``""`` = written by hand; e.g. ``jira``, ``confluence``, ``dynatrace``);
    ``repository``, ``path`` and ``lines`` only for code references."""
    title: str = Field(min_length=1)
    source: str = ""
    source_url: str = ""
    repository: str = ""
    path: str = ""
    lines: str = ""
    """E.g. ``10-40``; ``""`` = the whole file."""
    content: str = ""
