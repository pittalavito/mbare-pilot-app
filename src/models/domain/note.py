"""The types of a project's notes. On disk every note is a markdown file of
``notes/``; the type is in its name (``agent-task-<title>.md``,
``todo-list-<title>.md``, anything else is generic) and the typed ones follow
a template (domain/project/note_templates.py), shown by the app as a form."""
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
