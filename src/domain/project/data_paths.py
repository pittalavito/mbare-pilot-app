"""Where things live in the app's data home (``MBARE_PILOT_HOME``), and the
naming rules for notes and uploaded files. Pure functions: no filesystem here.

    definition/                      agents, chatbots, automations as YAML
      global-agent.yml               agents of the Library (global)
      global-chat-bot.yml            chatbot of every project that has none of its own
      global-automation.yml          automations of every project (unless it defines one with that name)
      project/<slug>/chat-bot.yml, agent.yml, automation.yml
    project/<slug>/
      notes/                         notes written in the app
      files/                         uploaded files
      context/                       the project's context: read_context, the RAG later"""
import re
from pathlib import PurePath

from core.error import ValidationError

NOTES_DIR = "notes"
FILES_DIR = "files"
CONTEXT_DIR = "context"
"""Markdown files about the project, written by hand (tool read_context)."""
NOTE_SUFFIX = ".md"

GLOBAL_AGENTS_FILE = "global-agent.yml"
GLOBAL_CHATBOT_FILE = "global-chat-bot.yml"
GLOBAL_AUTOMATIONS_FILE = "global-automation.yml"
CHATBOT_FILE = "chat-bot.yml"
AGENTS_FILE = "agent.yml"
AUTOMATIONS_FILE = "automation.yml"
"""Under ``definition/project/<slug>/``."""

_NOT_SLUG = re.compile(r"[^a-z0-9]+")
_INVALID_FILE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def project_slug(project_name: str) -> str:
    """Folder name of a project's data: lowercase, ``-`` separated (``"My App"`` → ``my-app``)."""
    slug = _NOT_SLUG.sub("-", project_name.lower()).strip("-")
    return slug or "project"


def project_definitions(project_name: str) -> str:
    """The project's folder of definitions, relative to ``definition/``."""
    return f"project/{project_slug(project_name)}"


def note_file_name(note_name: str) -> str:
    """``"Setup"`` / ``"setup.md"`` → ``setup.md``; rejects path separators and reserved chars."""
    name = note_name.strip()
    if name.lower().endswith(NOTE_SUFFIX):
        name = name[: -len(NOTE_SUFFIX)].strip()
    return _checked(name, "nota") + NOTE_SUFFIX


def data_file_name(file_name: str) -> str:
    """Base name of an uploaded file (any directory part is dropped), checked."""
    return _checked(PurePath(file_name.replace("\\", "/")).name.strip(), "file")


def _checked(name: str, what: str) -> str:
    if not name or name in {".", ".."} or _INVALID_FILE_CHARS.search(name) or name.startswith("."):
        raise ValidationError(f"Nome di {what} non valido: {name!r}")
    return name
