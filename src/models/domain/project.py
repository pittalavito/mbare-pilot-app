"""Project domain models: a project is a named folder on disk the agents work on."""
from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, Field, StringConstraints, field_validator

from models.domain.chat import EmbeddingModelName
from models.domain.dev import TestScope
from models.domain.note import NoteType

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class ProjectSource(StrEnum):
    """Where a project comes from."""
    FOLDER = "folder"
    """An existing folder opened as a project."""
    SCRATCH = "scratch"
    """A new, empty folder created for the project."""


DEFAULT_VISIBLE_NOTE_TYPES = [NoteType.GENERIC, NoteType.AGENT_TASK, NoteType.ACTIVITY]
"""The references stay inside the tasks and activities that link them."""


class CommandRequest(BaseModel):
    """A command the Operator wanted to run and may not (yet)."""
    repository: str = ""
    command: str


class Project(BaseModel):
    name: Name
    description: str = ""
    source: ProjectSource
    root_path: str
    """Absolute path of the project folder."""
    embedding_model: EmbeddingModelName = EmbeddingModelName.OPENAI_TEXT_EMBEDDING_3_SMALL
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    visible_note_types: list[NoteType] | None = None
    """The note types the Dati tab shows; None = DEFAULT_VISIBLE_NOTE_TYPES."""

    files_visible: bool = True
    """The Dati tab shows the uploaded files (they stay on disk either way)."""
    due_soon_days: int = Field(default=3, ge=0, le=60)
    """«📌 Oggi»: items due within this many days are «In scadenza»."""
    test_scope: TestScope = TestScope.ALL
    """«Verifica sviluppo»: every test or only the touched ones, unless the task says otherwise."""
    test_commands: dict[str, str] = {}
    """«Verifica sviluppo»: the tests' command per repository (folder → command); missing = detected."""
    auto_retries: int = Field(default=1, ge=0, le=3)
    """«Lavora attività»: how many times failed tests go back to Copilot by themselves (plan 12b)."""
    allowed_commands: list[str] = []
    """The commands the Operator may run with run_command (plan 11), as written."""
    command_requests: list[CommandRequest] = []
    """Commands the Operator asked for, waiting for the user's ok."""
    command_grants: list[str] = []
    """Commands allowed «Solo stavolta»: each is used up by its next run."""
    operator_chatbot_id: int | None = None
    """The Operator of the preparation before Copilot; None = the project's first one."""

    @field_validator("visible_note_types", mode="before")
    @classmethod
    def _old_todo_list(cls, value: Any) -> Any:
        """Saved before the todo lists became activities."""
        return [("activity" if item == "todo_list" else item) for item in value] if isinstance(value, list) else value


class ProjectDataKind(StrEnum):
    NOTE = "note"
    """Markdown note written in the app."""
    FILE = "file"
    """Uploaded document."""


class ProjectDataFile(BaseModel):
    """One item of a project's data folder."""
    name: str
    kind: ProjectDataKind
    size: int
    modified_at: datetime
    note_type: NoteType | None = None
    """For a note: its type, from its name."""
