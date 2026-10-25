"""Response models of the definitions sync (/projects/{project}/definitions/sync)."""
from pydantic import BaseModel

from models.domain.definitions import SyncItem, SyncReport


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
