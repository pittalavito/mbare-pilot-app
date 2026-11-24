"""Where things live in the app's data home (``MBARE_PILOT_HOME``), and the
naming rules for notes and uploaded files. Pure functions: no filesystem here.

    definition/                      the user's definitions, same layout as resource/definition
      agents/agents.yml              agents of the Library (global)
      agents/chatbots.yml            chatbots of every project (unless it has one with that name)
      automations/automations.yml    automations of every project (unless it defines one with that name)
      coding-agents/copilot/         coding-agent.yml (Copilot's prompts, denied tools, models) and prompts/<name>.md
      coding-agents/claude/          tool-requests.md: what Claude Code is told on the dev MCP server
      templates/<type>.md            the drafts' templates (confluence.md, jira.md)
      context/<topic>.md             the agents' general context
      code-search/searches.yml       the saved searches in the code
      board/roadmap.yml              the board of Mbare Pilot
      project/<slug>/                the same files for one project (agents/, automations/, coding-agents/copilot/, templates/)
    project/<slug>/
      notes/                         notes written in the app; the type is in the name:
                                     agent-task-<title>.md, attivita-<title>.md,
                                     code-reference-<title>.md, context-reference-<title>.md, else generic
      files/                         uploaded files
      context/                       the project's context: read_context, the RAG later
      copilot/<task>/                Copilot's working folder for a task delegated without a repository

Nothing is written in the repositories Copilot works on."""
import re
from pathlib import PurePath

from core.error import ValidationError
from models.domain.note import NoteType

NOTES_DIR = "notes"
FILES_DIR = "files"
CONTEXT_DIR = "context"
COPILOT_DIR = "copilot"
"""Copilot's working folders for the tasks delegated without a repository."""
NOTE_SUFFIX = ".md"
NOTE_PREFIXES = {
    NoteType.AGENT_TASK: "agent-task-",
    NoteType.ACTIVITY: "attivita-",
    NoteType.CODE_REFERENCE: "code-reference-",
    NoteType.CONTEXT_REFERENCE: "context-reference-",
}
"""The name of a typed note starts with the prefix of its type."""

AGENTS_FILE = "agents/agents.yml"
CHATBOTS_FILE = "agents/chatbots.yml"
AUTOMATIONS_FILE = "automations/automations.yml"
CODING_AGENT_FILE = "coding-agents/copilot/coding-agent.yml"
"""Copilot's prompts and denied tools; the global one is required to use Copilot."""
CODING_AGENT_PROMPTS_DIR = "coding-agents/copilot/prompts"
"""Planning prompts to choose from when delegating (``<name>.md``)."""
TEMPLATES_DIR = "templates"
"""The drafts' templates (``<type>.md``)."""
CLAUDE_TOOL_REQUESTS_FILE = "coding-agents/claude/tool-requests.md"
"""What Claude Code is told on the dev MCP server."""
ROADMAP_FILE = "board/roadmap.yml"
SEARCHES_FILE = "code-search/searches.yml"
"""Every path is relative to ``definition/`` (global) or to ``definition/project/<slug>/``
(the project's; only agents, chatbots, automations, Copilot and templates)."""
LEGACY_FILES = ("global-agent.yml", "global-chat-bots.yml", "global-automation.yml", "global-coding-agent.yml",
                "coding-agent", "code-searches.yml", "roadmap.yml")
LEGACY_PROJECT_FILES = ("agent.yml", "chat-bots.yml", "automation.yml", "coding-agent.yml", "coding-agent")
"""Names of an old layout, no longer read: reported at startup when found in the user's layer."""

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


FILE_LINK_PREFIX = "files/"
"""How a task or an activity links an uploaded file: ``files/<name>`` (the
path it gets in the task's folder for Copilot too). A note is linked by its name."""


def is_file_link(name: str) -> bool:
    return name.strip().replace("\\", "/").startswith(FILE_LINK_PREFIX)


def file_link(file_name: str) -> str:
    """``specifiche.pdf`` (or ``files/specifiche.pdf``) → ``files/specifiche.pdf``."""
    return FILE_LINK_PREFIX + data_file_name(file_name)


def data_file_name(file_name: str) -> str:
    """Base name of an uploaded file (any directory part is dropped), checked."""
    return _checked(PurePath(file_name.replace("\\", "/")).name.strip(), "file")


def _checked(name: str, what: str) -> str:
    if not name or name in {".", ".."} or _INVALID_FILE_CHARS.search(name) or name.startswith("."):
        raise ValidationError(f"Nome di {what} non valido: {name!r}")
    return name
