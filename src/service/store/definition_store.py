"""The definition files in two layers: the app's defaults
(``resource/definition``, versioned with the code) and the user's
(``<data_home>/definition``): what the user changes and the projects' files.
A file of the user's layer wins over the app's at the same path; the YAML
lists of the global files are merged by name by DefinitionService (it reads
both layers with ``read_layers``). Writes go to the user's layer only.
Satisfies ``coding_agent.DefinitionFiles``."""
from pathlib import Path

from domain.store.files.store import LocalFileRepository

APP = "app"
USER = "tuo"


class DefinitionStore:

    def __init__(self, root: Path, defaults: Path | None = None):
        self._files = LocalFileRepository(root)
        self._defaults = LocalFileRepository(defaults) if defaults is not None and defaults.is_dir() else None

    def read_definition(self, path: str) -> str | None:
        """A file (e.g. ``project/acme/agents/agents.yml``): the user's, else the app's; None when missing."""
        mine, app = self.read_layers(path)
        return mine if mine is not None else app

    def read_layers(self, path: str) -> tuple[str | None, str | None]:
        """The user's text and the app's text of ``path`` (None where missing)."""
        return _read(self._files, path), _read(self._defaults, path)

    def origin(self, path: str) -> str | None:
        """``tuo`` (the user's layer), ``app`` or None when missing."""
        if self._files.get(path) is not None:
            return USER
        return APP if self._defaults is not None and self._defaults.get(path) is not None else None

    def list_definitions(self, folder: str) -> list[str]:
        """The files directly in ``<folder>`` of both layers, as paths relative to ``definition/``."""
        prefix = folder.strip("/")
        found = set()
        for files in (self._files, self._defaults):
            if files is not None:
                found |= {stored.file_id for stored in files.list(prefix) if stored.file_id.rsplit("/", 1)[0] == prefix}
        return sorted(found)

    def in_user_layer(self, path: str) -> bool:
        """A file, or a folder with files, at ``path`` in the user's layer."""
        return self._files.get(path) is not None or bool(self._files.list(path))

    def save_definition(self, path: str, text: str) -> None:
        """Into the user's layer."""
        self._files.save(path, text.encode("utf-8"))

    def delete_definition(self, path: str) -> bool:
        """The user's file (the app's, if any, is back); False when there was none."""
        if self._files.get(path) is None:
            return False
        self._files.delete(path)
        return True


def _read(files: LocalFileRepository | None, path: str) -> str | None:
    if files is None or files.get(path) is None:
        return None
    return files.read(path).decode("utf-8")
