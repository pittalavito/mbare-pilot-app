"""Filesystem access for project folders, confined to the configured roots
(``PROJECT_ROOTS``): browse folders, validate a chosen folder, create a new
one. Nothing outside the roots is ever read or written."""
import os
import re
from pathlib import Path

from core.error import ValidationError

_INVALID_FOLDER_NAME = re.compile(r'[<>:"/\\|?*]')


class FolderBrowser:

    def __init__(self, roots: list[Path]):
        self._roots = [root.resolve() for root in roots]

    @property
    def roots(self) -> list[Path]:
        return list(self._roots)

    def resolve(self, path: str | Path) -> Path:
        """Absolute folder for ``path``: must exist, be a directory and live
        inside one of the roots. Raises ValidationError otherwise."""
        raw = str(path).strip().strip('"')
        if not raw:
            raise ValidationError("Percorso vuoto.")
        candidate = Path(os.path.expandvars(os.path.expanduser(raw))).resolve()
        if not self.is_allowed(candidate):
            allowed = ", ".join(str(root) for root in self._roots)
            raise ValidationError(f"La cartella deve stare dentro: {allowed}")
        if not candidate.is_dir():
            raise ValidationError(f"Cartella inesistente: {candidate}")
        return candidate

    def is_allowed(self, path: Path) -> bool:
        return any(path == root or path.is_relative_to(root) for root in self._roots)

    def parent(self, folder: Path) -> Path | None:
        """The parent folder, or None when ``folder`` is a root."""
        if folder in self._roots or not self.is_allowed(folder.parent):
            return None
        return folder.parent

    def subfolders(self, folder: Path, show_hidden: bool = False) -> list[Path]:
        """Readable subfolders, sorted by name (hidden ones only on request)."""
        try:
            children = [child for child in folder.iterdir() if child.is_dir()]
        except OSError:
            return []
        if not show_hidden:
            children = [child for child in children if not child.name.startswith(".")]
        return sorted(children, key=lambda child: child.name.lower())

    def create_folder(self, parent: str | Path, name: str) -> Path:
        """Create ``parent/name`` (``parent`` validated as above). The folder
        must not exist yet."""
        parent_folder = self.resolve(parent)
        name = name.strip()
        if not name or name in {".", ".."} or _INVALID_FOLDER_NAME.search(name):
            raise ValidationError(f"Nome di cartella non valido: {name!r}")
        folder = parent_folder / name
        if folder.exists():
            raise ValidationError(f"Esiste già: {folder}")
        folder.mkdir()
        return folder
