"""Where a project's data lives inside the app's data home
(``<MBARE_PILOT_HOME>/projects/<slug>/{notes,files}``), and the naming rules
for notes and uploaded files. Pure functions: no filesystem access here."""
import re
from pathlib import PurePath

from core.error import ValidationError

NOTES_DIR = "notes"
FILES_DIR = "files"
NOTE_SUFFIX = ".md"

_NOT_SLUG = re.compile(r"[^a-z0-9]+")
_INVALID_FILE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def project_slug(project_name: str) -> str:
    """Folder name of a project's data: lowercase, ``-`` separated (``"My App"`` → ``my-app``)."""
    slug = _NOT_SLUG.sub("-", project_name.lower()).strip("-")
    return slug or "project"


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
