"""The types of a project's notes. On disk every note is a markdown file of
``notes/``; the type is in its name (``agent-task-<title>.md``,
``attivita-<title>.md``, ``code-reference-<title>.md``,
``context-reference-<title>.md``, anything else is generic) and the typed ones
follow a template (domain/project/note_templates.py), shown by the app as a form.

References (code, context) are linked to agent tasks and activities by name
(their ``references``, many to many): they show only inside what links them.
An activity also links the agent tasks born from it (its ``agent_tasks``)."""
from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field


class NoteType(StrEnum):
    GENERIC = "generic"
    """Free markdown."""
    AGENT_TASK = "agent_task"
    """A task for an agent: objective, context, acceptance criteria, constraints."""
    ACTIVITY = "activity"
    """Something to do: a description, its todo list (priority and due date
    optional per item), the agent tasks born from it. Was the «todo list»."""
    CODE_REFERENCE = "code_reference"
    """A piece of code that matters for a task: repository, file, lines, why."""
    CONTEXT_REFERENCE = "context_reference"
    """Context for a task: text copied by hand or from Jira, Confluence, Dynatrace..."""

    @property
    def is_reference(self) -> bool:
        return self in (NoteType.CODE_REFERENCE, NoteType.CONTEXT_REFERENCE)


class TaskStatus(StrEnum):
    """In this order: created (by hand) and refinement (being refined with an
    agent, or created by the secretary) come before todo, ready to delegate;
    Copilot moves it to in_progress, then to_verify (a development: the user
    checks Copilot's changes and confirms) or done (the other types, when the
    user saves Copilot's answer as a note), or back to todo when it fails."""
    CREATED = "created"
    REFINEMENT = "refinement"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    TO_VERIFY = "to_verify"
    DONE = "done"

    @property
    def is_refined(self) -> bool:
        """Ready for an agent: past created and refinement."""
        return self not in (TaskStatus.CREATED, TaskStatus.REFINEMENT)


class TaskType(StrEnum):
    """What the task asks for; it picks Copilot's planning prompt
    (type_prompts) and how Copilot works on it (``plan_only``)."""
    DEVELOPMENT = "development"
    """Develop something: Copilot changes the code (planning, then execution)."""
    ANALYSIS = "analysis"
    """Analyse the code: Copilot reads and answers; the answer becomes a note."""
    CONFLUENCE = "confluence"
    """Write a Confluence page: Copilot writes the draft; it becomes a note."""
    JIRA = "jira"
    """Refine a Jira issue (was «refinement»): Copilot writes the draft; it becomes a note."""

    @property
    def plan_only(self) -> bool:
        """Copilot never changes the code: no execution, its answer is saved as a note."""
        return self != TaskType.DEVELOPMENT


class ChecklistItem(BaseModel):
    text: str
    done: bool = False


class AgentTask(BaseModel):
    title: str = Field(min_length=1)
    status: TaskStatus = TaskStatus.CREATED
    type: TaskType = TaskType.DEVELOPMENT
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
    agent_task: str | None = None
    """The agent task born from the item (``→ agent-task-….md`` on its line): when it gets done the item is checked."""


class ItemChange(BaseModel):
    """An item checked or unchecked by itself, because its agent task got or left «done»."""
    activity: str
    activity_title: str
    item: int
    """1-based."""
    text: str
    done: bool


class ActivityStatus(StrEnum):
    """Set by hand (or by the secretary); when every item is done the editor suggests «done»."""
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class Activity(BaseModel):
    title: str = Field(min_length=1)
    status: ActivityStatus = ActivityStatus.TODO
    description: str = ""
    items: list[TodoItem] = []
    """Its todo list."""
    agent_tasks: list[str] = []
    """The agent tasks born from it, by note name (the one place the link is written)."""
    references: list[str] = []
    """The linked reference notes, by name."""
    learned: str = ""
    """What the user learned (``## Imparato``, written when done): a done
    activity with it enters the project's context index (RAG)."""


class TaskLink(BaseModel):
    """Something an agent task links in ``## Riferimenti``, as Copilot lists it (MCP)."""
    name: str
    """As the task writes it: a note's name or ``files/<name>``."""
    kind: str
    """``code``, ``context`` (references), ``note`` (a generic note) or ``file`` (an uploaded file)."""
    title: str
    found: bool = True
    """False when it no longer exists (deleted by hand)."""


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
