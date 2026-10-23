"""Filesystem persistence base for the local files store: the ``FileStore`` base
every concrete file repository extends. It owns a single root directory and
safe path resolution under it (no traversal outside the root)."""
from pathlib import Path

from core.error import ValidationError


class FileStore:
    """A safe root directory plus path resolution confined to it."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _safe_path(self, relative_path: str) -> Path:
        """Absolute path for ``relative_path``, guaranteed to stay under the root."""
        candidate = (self.root / relative_path.replace("\\", "/").strip("/")).resolve()
        if self.root not in candidate.parents:
            raise ValidationError("Invalid path: traversal outside the store root is not allowed.")
        return candidate

    def _relative(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()
