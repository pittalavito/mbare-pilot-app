"""Request/response models of a project's data API: notes (generic, agent
tasks, activities, code and context references) and uploaded files."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from models.domain.note import (
    Activity,
    ActivityStatus,
    AgentTask,
    ChecklistItem,
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


class ItemTaskBody(BaseModel):
    """«🤖» on an item: the task to create from it (checked against the item's text)."""
    text: str
    type: TaskType = TaskType.DEVELOPMENT


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
    learned: str = ""
    """What was learned (``## Imparato``): a done activity with it enters the context index."""

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


class CodeTodoScanResponse(BaseModel):
    """What a scan of the todoMbarePilot comments wrote: counts only, the comments are in the note."""
    note: str | None
    """The code reference written; None = nothing found and no note to update."""
    created: bool
    files: int
    comments: int
    malformed: int = 0
    """Comments written wrong: listed in the note, to fix."""


# ------------------------------------------------------------------ context

class ContextSavedResponse(BaseModel):
    name: str
    index_error: str | None = None
    """Why the document could not be indexed (e.g. no embedder key); None when it was (or did not change)."""


class ContextSearchRequest(BaseModel):
    question: str
