"""Definitions as files (agents, chatbot, automations as YAML in the data
folder): GET /projects/{project}/definitions previews them, POST .../sync
applies them (all, or the elements chosen from the preview)."""
from fastapi import APIRouter, Body, Depends

from controller.dependencies import definition_service
from models.controller.definitions import DefinitionEntryResponse, SyncReportResponse, SyncRequest
from service.definition_service import DefinitionService

router = APIRouter(prefix="/projects/{project}/definitions", tags=["definitions"])


@router.get("")
def preview_definitions(project: str, service: DefinitionService = Depends(definition_service)) -> list[DefinitionEntryResponse]:
    """What the files define, nothing applied: each element new, already there or with its error."""
    return [DefinitionEntryResponse.from_entry(entry) for entry in service.preview(project)]


@router.post("/sync")
def sync_definitions(
    project: str, request: SyncRequest | None = Body(default=None), service: DefinitionService = Depends(definition_service),
) -> SyncReportResponse:
    """Create or update what the project's files define (the file wins): all,
    or ``only`` the elements chosen from the preview. One item per element,
    errors included (an element with errors is skipped)."""
    only = [key.to_key() for key in request.only] if request and request.only is not None else None
    return SyncReportResponse.from_report(service.sync(project, only))
