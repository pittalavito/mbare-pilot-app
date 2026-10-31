"""The projects' files on disk (``<data_home>/project``): notes, context
files, Copilot's tasks, ... by id (a path relative to that folder). The files
are already the domain shape (``StoredFile``): no mapper."""
from pathlib import Path

from domain.store.files.store import LocalFileRepository, StoredFile


class ProjectFileStore:

    def __init__(self, root: Path):
        self._files = LocalFileRepository(root)

    def list(self, prefix: str = "") -> list[StoredFile]:
        return self._files.list(prefix)

    def save(self, file_id: str, data: bytes) -> StoredFile:
        return self._files.save(file_id, data)

    def get(self, file_id: str) -> StoredFile | None:
        return self._files.get(file_id)

    def read(self, file_id: str) -> bytes:
        return self._files.read(file_id)

    def delete(self, file_id: str) -> bool:
        return self._files.delete(file_id)

    def path(self, file_id: str) -> Path:
        """Where ``file_id`` is on disk: for a program that reads it itself (Copilot's --add-dir)."""
        return self._files.path(file_id)

    def delete_folder(self, prefix: str) -> bool:
        """A folder of the file store with everything in it."""
        return self._files.delete_tree(prefix)
