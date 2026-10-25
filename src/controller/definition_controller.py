"""Definitions as files (agents, chatbot, automations as YAML in the context
repo): POST /projects/{project}/definitions/sync applies them."""
from fastapi import APIRouter, Depends

from controller.dependencies import definition_service
from models.controller.definitions import SyncReportResponse
from service.definition_service import DefinitionService

router = APIRouter(prefix="/projects/{project}/definitions", tags=["definitions"])


@router.post("/sync")
def sync_definitions(project: str, service: DefinitionService = Depends(definition_service)) -> SyncReportResponse:
    """Create or update what the project's files define (the file wins); one
    item per file, errors included (a file with errors is skipped)."""
    return SyncReportResponse.from_report(service.sync(project))
