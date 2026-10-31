"""Masking of sensitive values before they reach an LLM, per project.

Values enter a project's map automatically (every run of a project registers
the project's repository names before the LLM sees anything; the sensitive
fields of the tools' outputs are registered by the agent layer) or by hand
(Impostazioni → Mascheramento). AgentService runs every project's agent through
an ``AgentMask`` (domain/agent/masking.py), which opens a ``MaskSession`` here:
the input and the conversation are masked, the tools get unmasked arguments and
return masked output, the answer is unmasked before it is saved and shown."""
from typing import Any

from pydantic import BaseModel

from core.error import NotFoundError, ValidationError
from domain.masking.masker import Masker
from models.domain.masking import MaskCategory, MaskEntry, sensitive_values
from service.store.mask_store import MaskStore
from service.store_service import StoreService

MIN_LENGTH = 3
"""Shorter values are not masked: they would match too much."""


class MaskingService:

    def __init__(self, store_service: StoreService, masks: MaskStore):
        self._store = store_service
        self._masks = masks

    def entries(self, project_name: str) -> list[MaskEntry]:
        """The project's map, by category then alias number."""
        return self._masks.list(project_name)

    def register(self, project_name: str, category: MaskCategory, value: str) -> MaskEntry | None:
        """A value found by a tool; None when too short to be masked."""
        value = value.strip()
        if len(value) < MIN_LENGTH:
            return None
        return self._masks.add(project_name, category, value, manual=False)

    def register_declared(self, project_name: str, output: BaseModel) -> None:
        """The values ``output`` declares sensitive (its Mask* fields, see
        models.domain.masking), e.g. what a function step read: masked for
        the agent steps that follow."""
        for category, value in sensitive_values(output):
            self.register(project_name, category, value)

    def add_term(self, project_name: str, category: MaskCategory, value: str) -> MaskEntry:
        """A value added by hand; already in the map = returned as it is."""
        if self._store.get_project(project_name) is None:
            raise NotFoundError(f"Progetto non trovato: {project_name}")
        value = value.strip()
        if len(value) < MIN_LENGTH:
            raise ValidationError(f"Il valore da mascherare deve avere almeno {MIN_LENGTH} caratteri.")
        return self._masks.add(project_name, category, value, manual=True)

    def remove(self, project_name: str, alias: str) -> None:
        """The value goes back to the LLM in clear; its alias is never reused."""
        if not self._masks.delete(project_name, alias):
            raise NotFoundError(f"Alias non trovato: {alias}")

    def session(self, project_name: str) -> "MaskSession":
        return MaskSession(self, project_name)


class MaskSession:
    """The masking of one run: the project's map, refreshed when a tool
    registers a new value during the run."""

    def __init__(self, service: MaskingService, project_name: str):
        self._service = service
        self._project_name = project_name
        self._masker = Masker(service.entries(project_name))

    def mask(self, text: str) -> str:
        return self._masker.mask(text)

    def unmask(self, text: str) -> str:
        return self._masker.unmask(text)

    def unmask_value(self, value: Any) -> Any:
        """Tool arguments: strings unmasked, also inside lists, tuples and dicts."""
        if isinstance(value, str):
            return self.unmask(value)
        if isinstance(value, dict):
            return {key: self.unmask_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return type(value)(self.unmask_value(item) for item in value)
        return value

    def register_all(self, category: MaskCategory, values: list[str]) -> None:
        """Add several values at once (the map is reloaded once)."""
        added = [self._service.register(self._project_name, category, value) for value in values]
        if any(entry is not None for entry in added):
            self._masker = Masker(self._service.entries(self._project_name))
