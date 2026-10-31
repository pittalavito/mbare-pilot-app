"""The definition files (``<data_home>/definition``): the YAML of the global
and project agents, chatbots and automations, Copilot's prompts. They are text
the user edits by hand, read as it is; DefinitionService validates and applies
them. Satisfies ``coding_agent.DefinitionFiles``."""
from pathlib import Path

from domain.store.files.store import LocalFileRepository


class DefinitionStore:

    def __init__(self, root: Path):
        self._files = LocalFileRepository(root)

    def read_definition(self, path: str) -> str | None:
        """A file under ``<data_home>/definition`` (e.g. ``project/acme/agent.yml``); None when missing."""
        if self._files.get(path) is None:
            return None
        return self._files.read(path).decode("utf-8")

    def list_definitions(self, folder: str) -> list[str]:
        """The files directly in ``<data_home>/definition/<folder>``, as paths relative to ``definition/``."""
        prefix = folder.strip("/")
        return [stored.file_id for stored in self._files.list(prefix)
                if stored.file_id.rsplit("/", 1)[0] == prefix]

    def save_definition(self, path: str, text: str) -> None:
        self._files.save(path, text.encode("utf-8"))
