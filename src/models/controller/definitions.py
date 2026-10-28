"""Request/response models of the definitions: the preview (/projects/{project}/definitions) and the sync (.../sync)."""
from pydantic import BaseModel

from models.domain.definitions import DefinitionEntry, DefinitionKey, DefinitionKind, SyncItem, SyncReport


class SyncItemResponse(BaseModel):
    kind: str
    """``agent`` | ``chatbot`` | ``automation``."""
    file: str
    name: str | None
    outcome: str
    """``created`` | ``updated`` | ``unchanged`` | ``error``."""
    message: str

    @classmethod
    def from_item(cls, item: SyncItem) -> "SyncItemResponse":
        return cls(kind=item.kind.value, file=item.file, name=item.name, outcome=item.outcome.value, message=item.message)


class SyncReportResponse(BaseModel):
    project_name: str
    items: list[SyncItemResponse]

    @classmethod
    def from_report(cls, report: SyncReport) -> "SyncReportResponse":
        return cls(project_name=report.project_name, items=[SyncItemResponse.from_item(item) for item in report.items])


class DefinitionKeyRequest(BaseModel):
    """An element to sync, as the preview lists it."""
    kind: DefinitionKind
    file: str
    name: str | None

    def to_key(self) -> DefinitionKey:
        return DefinitionKey(kind=self.kind, file=self.file, name=self.name)


class SyncRequest(BaseModel):
    only: list[DefinitionKeyRequest] | None = None
    """Just these elements; omitted = everything the files define."""


class DefinitionEntryResponse(BaseModel):
    kind: DefinitionKind
    file: str
    name: str | None
    state: str
    """``new`` (a sync creates it) | ``exists`` (a sync updates it: the file wins) | ``error`` (skipped)."""
    message: str

    @classmethod
    def from_entry(cls, entry: DefinitionEntry) -> "DefinitionEntryResponse":
        return cls(kind=entry.kind, file=entry.file, name=entry.name, state=entry.state.value, message=entry.message)
