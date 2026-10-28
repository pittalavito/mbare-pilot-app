"""Request/response models of a project's data API: notes (generic, agent
tasks, todo lists, code and context references) and uploaded files."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from models.domain.note import AgentTask, ChecklistItem, NoteType, Reference, TaskStatus, TodoItem, TodoList, TodoPriority
from models.domain.project import ProjectDataFile


class DataFileResponse(BaseModel):
    name: str
    kind: str
    """``note`` | ``file``."""
    size: int
    modified_at: datetime
    note_type: str | None = None
    """For a note: ``generic`` | ``agent_task`` | ``todo_list`` | ``code_reference`` | ``context_reference``."""

    @classmethod
    def from_file(cls, item: ProjectDataFile) -> "DataFileResponse":
        return cls(**item.model_dump())


class NoteResponse(BaseModel):
    name: str
    content: str


class NoteRequest(BaseModel):
    content: str


# -------------------------------------------------------------- typed notes

class ChecklistItemBody(BaseModel):
    text: str
    done: bool = False


class AgentTaskBody(BaseModel):
    title: str = Field(min_length=1)
    status: TaskStatus = TaskStatus.TODO
    objective: str = ""
    context: str = ""
    criteria: list[ChecklistItemBody] = []
    constraints: str = ""
    references: list[str] = []
    """The linked reference notes, by name."""

    def to_task(self) -> AgentTask:
        return AgentTask(**self.model_dump(exclude={"criteria"}), criteria=[ChecklistItem(**item.model_dump()) for item in self.criteria])


class AgentTaskResponse(AgentTaskBody):
    name: str
    """The note's file name (``agent-task-<title>.md``): it identifies the task."""

    @classmethod
    def from_task(cls, name: str, task: AgentTask) -> "AgentTaskResponse":
        return cls(name=name, **task.model_dump())


class TodoItemBody(ChecklistItemBody):
    priority: TodoPriority | None = None
    due: date | None = None


class TodoListBody(BaseModel):
    title: str = Field(min_length=1)
    items: list[TodoItemBody] = []
    references: list[str] = []
    """The linked reference notes, by name."""

    def to_todo(self) -> TodoList:
        return TodoList(title=self.title, items=[TodoItem(**item.model_dump()) for item in self.items], references=self.references)


class TodoListResponse(TodoListBody):
    name: str
    """The note's file name (``todo-list-<title>.md``): it identifies the list."""

    @classmethod
    def from_todo(cls, name: str, todo: TodoList) -> "TodoListResponse":
        return cls(name=name, **todo.model_dump())


# --------------------------------------------------------------- references

class ReferenceBody(BaseModel):
    title: str = Field(min_length=1)
    source: str = ""
    """Where it was copied from: ``""`` = by hand, e.g. ``jira``, ``confluence``, ``dynatrace``."""
    source_url: str = ""
    repository: str = ""
    """Code references only, as ``path`` and ``lines``."""
    path: str = ""
    lines: str = ""
    content: str = ""

    def to_reference(self) -> Reference:
        return Reference(**self.model_dump())


class ReferenceCreateBody(ReferenceBody):
    kind: Literal["code_reference", "context_reference"]


class ReferenceResponse(ReferenceBody):
    name: str
    """The note's file name (``code-reference-<title>.md``...): it identifies the reference."""
    kind: str
    """``code_reference`` | ``context_reference``."""
    linked_from: list[str]
    """The agent tasks and todo lists that link it."""

    @classmethod
    def from_reference(cls, name: str, kind: NoteType, reference: Reference, linked_from: list[str]) -> "ReferenceResponse":
        return cls(name=name, kind=kind.value, linked_from=linked_from, **reference.model_dump())
