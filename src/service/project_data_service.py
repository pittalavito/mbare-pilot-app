"""A project's data, kept by the app apart from the project's code:
``<MBARE_PILOT_HOME>/projects/<slug>/notes/*.md`` (notes written in the app)
and ``.../files/*`` (uploaded documents). These are the sources the RAG index
will be built from."""
from datetime import datetime, timezone

from core.error import NotFoundError
from domain.project.data_paths import (
    CHATBOT_DIR, CHATBOT_PROMPT_FILE, FILES_DIR, NOTE_SUFFIX, NOTES_DIR, data_file_name, note_file_name, project_slug,
)
from models.domain.project import ProjectDataFile, ProjectDataKind
from models.store.files import StoredFile
from service.store_service import StoreService


class ProjectDataService:

    def __init__(self, store_service: StoreService):
        self._store = store_service

    # ----------------------------------------------------------------- notes
    def list_notes(self, project_name: str) -> list[ProjectDataFile]:
        return self._list(project_name, NOTES_DIR, ProjectDataKind.NOTE)

    def read_note(self, project_name: str, note_name: str) -> str:
        return self._store.read_file(self._id(project_name, NOTES_DIR, note_file_name(note_name))).decode("utf-8")

    def save_note(self, project_name: str, note_name: str, content: str) -> ProjectDataFile:
        """Create or overwrite the note."""
        stored = self._store.save_file(
            self._id(project_name, NOTES_DIR, note_file_name(note_name)), content.encode("utf-8"),
        )
        return _to_data_file(stored, ProjectDataKind.NOTE)

    def delete_note(self, project_name: str, note_name: str) -> bool:
        return self._store.delete_file(self._id(project_name, NOTES_DIR, note_file_name(note_name)))

    # ----------------------------------------------------------------- files
    def list_files(self, project_name: str) -> list[ProjectDataFile]:
        return self._list(project_name, FILES_DIR, ProjectDataKind.FILE)

    def read_file(self, project_name: str, file_name: str) -> bytes:
        return self._store.read_file(self._id(project_name, FILES_DIR, data_file_name(file_name)))

    def save_file(self, project_name: str, file_name: str, data: bytes) -> ProjectDataFile:
        """Store an uploaded file (same name = overwritten)."""
        stored = self._store.save_file(self._id(project_name, FILES_DIR, data_file_name(file_name)), data)
        return _to_data_file(stored, ProjectDataKind.FILE)

    def delete_file(self, project_name: str, file_name: str) -> bool:
        return self._store.delete_file(self._id(project_name, FILES_DIR, data_file_name(file_name)))

    # --------------------------------------------------------------- chatbot
    def chatbot_context(self, project_name: str) -> dict[str, str]:
        """The project's context for its chatbot: the ``.md`` files of
        ``chat-bot/`` (not its system prompt), name -> content."""
        prefix = f"{project_slug(self._project(project_name))}/{CHATBOT_DIR}"
        return {
            stored.file_id.rsplit("/", 1)[-1]: self._store.read_file(stored.file_id).decode("utf-8")
            for stored in sorted(self._store.list_files(prefix), key=lambda item: item.file_id.lower())
            if stored.file_id.endswith(NOTE_SUFFIX) and not stored.file_id.endswith(f"/{CHATBOT_PROMPT_FILE}")
        }

    # --------------------------------------------------------------- helpers
    def _project(self, project_name: str) -> str:
        project = self._store.get_project(project_name)
        if project is None:
            raise NotFoundError(f"Progetto non trovato: {project_name}")
        return project.name

    def _id(self, project_name: str, folder: str, file_name: str) -> str:
        return f"{project_slug(self._project(project_name))}/{folder}/{file_name}"

    def _list(self, project_name: str, folder: str, kind: ProjectDataKind) -> list[ProjectDataFile]:
        prefix = f"{project_slug(self._project(project_name))}/{folder}"
        return sorted(
            (_to_data_file(stored, kind) for stored in self._store.list_files(prefix)),
            key=lambda item: item.name.lower(),
        )


def _to_data_file(stored: StoredFile, kind: ProjectDataKind) -> ProjectDataFile:
    return ProjectDataFile(
        name=stored.file_id.rsplit("/", 1)[-1],
        kind=kind,
        size=stored.size,
        modified_at=datetime.fromtimestamp(stored.mtime_ns / 1e9, tz=timezone.utc),
    )
