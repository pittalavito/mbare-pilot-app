"""Request/response models of a project's data API: notes (generic, agent
tasks, activities, code and context references) and uploaded files."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from models.domain.code_search import CodeQuery
from models.domain.dev import TestScope
from models.domain.note import (
    Activity,
    ActivityStatus,
    AgentTask,
    ChecklistItem,
    DevPhase,
    ItemChange,
    NoteType,
    Reference,
    TaskStatus,
    TaskType,
    TodoItem,
    TodoPriority,
)
from models.domain.project import ProjectDataFile


class DataFileResponse(BaseModel):
    name: str
    kind: str
    """``note`` | ``file``."""
    size: int
    modified_at: datetime
    note_type: str | None = None
    """For a note: ``generic`` | ``agent_task`` | ``activity`` | ``code_reference`` | ``context_reference``."""

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
    status: TaskStatus = TaskStatus.CREATED
    type: TaskType = TaskType.DEVELOPMENT
    objective: str = ""
    context: str = ""
    criteria: list[ChecklistItemBody] = []
    constraints: str = ""
    references: list[str] = []
    """The linked reference notes, by name."""
    tests: TestScope | None = None
    """``run_tests``: ``all`` or ``touched`` tests; null = the project's default."""
    pre: DevPhase = DevPhase()
    """A development's Pre (plan 34): steps, commands, automation; before the delegation."""
    post: DevPhase = DevPhase()
    """A development's Post (plan 34): after the final confirmation."""
    publish_space: str = ""
    """A Confluence task's space for a new page (plan 32)."""
    publish_parent: str = ""
    """A Confluence task's parent page or folder (id or link) for a new page (plan 32)."""

    def to_task(self) -> AgentTask:
        return AgentTask(**self.model_dump(exclude={"criteria"}), criteria=[ChecklistItem(**item.model_dump()) for item in self.criteria])


class AgentTaskResponse(AgentTaskBody):
    name: str
    """The note's file name (``agent-task-<title>.md``): it identifies the task."""

    @classmethod
    def from_task(cls, name: str, task: AgentTask) -> "AgentTaskResponse":
        return cls(name=name, **task.model_dump())


class AgentTaskSavedResponse(AgentTaskResponse):
    items_changed: list[ItemChange] = []
    """The items checked (the task got «done») or unchecked (it left it) by this save."""


class TodoItemBody(ChecklistItemBody):
    priority: TodoPriority | None = None
    due: date | None = None
    agent_task: str | None = None
    """The agent task born from the item (by name): it is checked when the task gets «done»."""


class ActivityBody(BaseModel):
    title: str = Field(min_length=1)
    status: ActivityStatus = ActivityStatus.TODO
    description: str = ""
    items: list[TodoItemBody] = []
    """Its todo list."""
    agent_tasks: list[str] = []
    """The agent tasks born from it, by name."""
    references: list[str] = []
    """The linked reference notes, by name."""

    def to_activity(self) -> Activity:
        return Activity(**self.model_dump(exclude={"items"}), items=[TodoItem(**item.model_dump()) for item in self.items])


class ActivityResponse(ActivityBody):
    name: str
    """The note's file name (``attivita-<title>.md``): it identifies the activity."""

    @classmethod
    def from_activity(cls, name: str, activity: Activity) -> "ActivityResponse":
        return cls(name=name, **activity.model_dump())


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
    """The agent tasks and activities that link it."""

    @classmethod
    def from_reference(cls, name: str, kind: NoteType, reference: Reference, linked_from: list[str]) -> "ReferenceResponse":
        return cls(name=name, kind=kind.value, linked_from=linked_from, **reference.model_dump())


# ----------------------------------------------------------------- settings

class DataSettingsBody(BaseModel):
    visible_note_types: list[NoteType]
    """The note types the Dati tab shows: ``generic``, ``agent_task``, ``activity``, ``code_reference``, ``context_reference``."""
    files_visible: bool = True
    """It shows the uploaded files too (they stay on disk either way)."""
    due_soon_days: int | None = Field(default=None, ge=0, le=60)
    """«📌 Oggi»: items due within this many days are «In scadenza»; omitted in a save = unchanged."""


class CodeSearchSaveBody(CodeQuery):
    """A code search to save as a code reference."""
    title: str = ""
    """The reference's title; empty = the text searched."""
    task: str = ""
    """The agent task (or activity) to link it to; empty = none."""


# ------------------------------------------------------------------ context

class ContextSavedResponse(BaseModel):
    name: str
    index_error: str | None = None
    """Why the document could not be indexed (e.g. no embedder key); None when it was (or did not change)."""


class ContextSearchRequest(BaseModel):
    question: str
