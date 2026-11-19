"""The links to a note in the app, as the agents write them: activities, agent
tasks and the WIP note are in «📋 Lavoro» (``/work``), the rest in «🗂️ Progetto»
(``/project``). The same rule as the UI's ``noteZone``."""
from urllib.parse import quote

from domain.project.data_paths import NOTE_PREFIXES
from domain.project.wip import WIP_NOTE
from models.domain.note import NoteType


def note_zone(note: str) -> str:
    work = note == WIP_NOTE or note.startswith((NOTE_PREFIXES[NoteType.ACTIVITY], NOTE_PREFIXES[NoteType.AGENT_TASK], "archivio-"))
    return "work" if work else "project"


def note_link(project_name: str, note: str) -> str:
    """The note in the app, in its zone."""
    return f"/projects/{quote(project_name)}/{note_zone(note)}?note={quote(note)}"
