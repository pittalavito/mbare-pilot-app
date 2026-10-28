"""Where things live in the app's data home (``MBARE_PILOT_HOME``), and the
naming rules for notes and uploaded files. Pure functions: no filesystem here.

    definition/                      agents, chatbots, automations as YAML
      global-agent.yml               agents of the Library (global)
      global-chat-bot.yml            chatbot of every project that has none of its own
      global-automation.yml          automations of every project (unless it defines one with that name)
      global-coding-agent.yml        Copilot's prompts, denied tools and models
      coding-agent/<name>.md         planning prompts to choose from when delegating
      project/<slug>/chat-bot.yml, agent.yml, automation.yml, coding-agent.yml, coding-agent/
    project/<slug>/
      notes/                         notes written in the app; the type is in the name:
                                     agent-task-<title>.md, todo-list-<title>.md,
                                     code-reference-<title>.md, context-reference-<title>.md, else generic
      files/                         uploaded files
      context/                       the project's context: read_context, the RAG later"""
import re
from pathlib import PurePath

from core.error import ValidationError
from models.domain.note import NoteType

NOTES_DIR = "notes"
FILES_DIR = "files"
CONTEXT_DIR = "context"
"""Markdown files about the project, written by hand (tool read_context)."""
NOTE_SUFFIX = ".md"
NOTE_PREFIXES = {
    NoteType.AGENT_TASK: "agent-task-",
    NoteType.TODO_LIST: "todo-list-",
    NoteType.CODE_REFERENCE: "code-reference-",
    NoteType.CONTEXT_REFERENCE: "context-reference-",
}
"""The name of a typed note starts with the prefix of its type."""

GLOBAL_AGENTS_FILE = "global-agent.yml"
GLOBAL_CHATBOT_FILE = "global-chat-bot.yml"
GLOBAL_AUTOMATIONS_FILE = "global-automation.yml"
GLOBAL_CODING_AGENT_FILE = "global-coding-agent.yml"
"""Copilot's prompts and denied tools; required to use Copilot."""
CHATBOT_FILE = "chat-bot.yml"
AGENTS_FILE = "agent.yml"
AUTOMATIONS_FILE = "automation.yml"
CODING_AGENT_FILE = "coding-agent.yml"
"""Under ``definition/project/<slug>/``."""
CODING_AGENT_PROMPTS_DIR = "coding-agent"
"""Planning prompts to choose from when delegating (``<name>.md``), under
``definition/`` and ``definition/project/<slug>/`` (the project's win by name)."""

_NOT_SLUG = re.compile(r"[^a-z0-9]+")
_INVALID_FILE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def slug(text: str, fallback: str) -> str:
    """Lowercase, ``-`` separated (``"My App"`` → ``my-app``); ``fallback`` when nothing is left."""
    return _NOT_SLUG.sub("-", text.lower()).strip("-") or fallback


def project_slug(project_name: str) -> str:
    """Folder name of a project's data."""
    return slug(project_name, "project")


def project_definitions(project_name: str) -> str:
    """The project's folder of definitions, relative to ``definition/``."""
    return f"project/{project_slug(project_name)}"


def note_file_name(note_name: str) -> str:
    """``"Setup"`` / ``"setup.md"`` → ``setup.md``; rejects path separators and reserved chars."""
    name = note_name.strip()
    if name.lower().endswith(NOTE_SUFFIX):
        name = name[: -len(NOTE_SUFFIX)].strip()
    return _checked(name, "nota") + NOTE_SUFFIX


def note_type(file_name: str) -> NoteType:
    """The type of a note, from its file name."""
    return next((kind for kind, prefix in NOTE_PREFIXES.items() if file_name.lower().startswith(prefix)), NoteType.GENERIC)


def typed_note_file_name(kind: NoteType, title: str) -> str:
    """``(AGENT_TASK, "Refactor login")`` → ``agent-task-refactor-login.md``."""
    return f"{NOTE_PREFIXES[kind]}{slug(title, 'senza-titolo')}{NOTE_SUFFIX}"


def data_file_name(file_name: str) -> str:
    """Base name of an uploaded file (any directory part is dropped), checked."""
    return _checked(PurePath(file_name.replace("\\", "/")).name.strip(), "file")


def _checked(name: str, what: str) -> str:
    if not name or name in {".", ".."} or _INVALID_FILE_CHARS.search(name) or name.startswith("."):
        raise ValidationError(f"Nome di {what} non valido: {name!r}")
    return name
