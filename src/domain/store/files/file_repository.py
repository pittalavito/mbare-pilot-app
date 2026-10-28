"""Generic files under the file store root, addressed by ``file_id`` (a path
relative to the root, e.g. ``uploads/report.pdf``). Callers pass ids, never
absolute paths."""
import shutil
from pathlib import Path

from core.error import NotFoundError
from domain.store.files.repository import FileStore
from models.store.files import StoredFile


class LocalFileRepository(FileStore):

    def __init__(self, root: Path):
        super().__init__(root)

    def list(self, prefix: str = "") -> list[StoredFile]:
        """Every file under ``prefix`` (the whole store by default)."""
        base = self._safe_path(prefix) if prefix else self.root
        if not base.is_dir():
            return []
        return [self._to_stored(path) for path in sorted(base.rglob("*")) if path.is_file() and path.name != ".gitkeep"]

    def get(self, file_id: str) -> StoredFile | None:
        path = self._safe_path(file_id)
        return self._to_stored(path) if path.is_file() else None

    def read(self, file_id: str) -> bytes:
        path = self._safe_path(file_id)
        if not path.is_file():
            raise NotFoundError(f"File not found: {file_id}")
        return path.read_bytes()

    def save(self, file_id: str, data: bytes) -> StoredFile:
        """Write (or overwrite) the file, creating parent folders."""
        path = self._safe_path(file_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return self._to_stored(path)

    def delete(self, file_id: str) -> bool:
        """True if a file was deleted."""
        path = self._safe_path(file_id)
        if not path.is_file():
            return False
        path.unlink()
        return True

    def path(self, file_id: str) -> Path:
        """The absolute path of ``file_id`` (a file or a folder), checked to stay under the root."""
        return self._safe_path(file_id)

    def delete_tree(self, prefix: str) -> bool:
        """The folder ``prefix`` with everything in it; True if it existed."""
        path = self._safe_path(prefix)
        if path == self.root or not path.is_dir():
            return False
        shutil.rmtree(path)
        return True

    def _to_stored(self, path: Path) -> StoredFile:
        stat = path.stat()
        return StoredFile(file_id=self._relative(path), size=stat.st_size, mtime_ns=stat.st_mtime_ns)
