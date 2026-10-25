"""Admin endpoints: the app config with secrets masked (/admin/config), the
observability facts (/observability/...: runs and tool calls from Postgres,
the verbatim trace of a run from Redis) and the DB backups (/admin/backups)."""
from typing import Any
from fastapi import APIRouter, Depends, Response, status

from core.error import NotFoundError
from config import Config
from controller.dependencies import backup_service, store_service
from service.backup_service import BackupService
from service.store_service import StoreService
from models.controller.admin import BackupResponse, BackupsResponse, ConfigResponse, RunSummaryResponse, ToolCallResponse

router = APIRouter(tags=["admin"])


@router.get("/admin/config")
def app_config() -> ConfigResponse:
    config = Config.get()    
    return ConfigResponse(
        settings=config.masked(),
        redis_dashboard_port=config.redis_dashboard_port,
        postgres_dashboard_port=config.postgres_dashboard_port,
    )


@router.get("/observability/runs")
def list_runs(limit: int = 100, store: StoreService = Depends(store_service)) -> list[RunSummaryResponse]:
    """Newest first."""
    return [RunSummaryResponse.from_summary(summary) for summary in store.list_runs(limit)]


@router.get("/observability/runs/{run_id}/trace")
def run_trace(run_id: str, store: StoreService = Depends(store_service)) -> dict[str, Any]:
    """Input, output, tool calls and LLM generations, as recorded."""
    trace = store.get_run_trace(run_id)
    if trace is None:
        raise NotFoundError(f"Trace non trovato: {run_id}")
    return trace.model_dump(mode="json")


@router.get("/observability/tool-calls")
def list_tool_calls(limit: int = 100, store: StoreService = Depends(store_service)) -> list[ToolCallResponse]:
    return [ToolCallResponse.from_summary(summary) for summary in store.list_tool_calls(limit)]


@router.get("/admin/backups")
def list_backups(service: BackupService = Depends(backup_service)) -> BackupsResponse:
    return BackupsResponse(
        folder=str(Config.get().backup_path),
        backups=[BackupResponse.from_backup(backup) for backup in service.list_backups()],
    )


@router.post("/admin/backups", status_code=status.HTTP_201_CREATED)
def export_db(service: BackupService = Depends(backup_service)) -> BackupResponse:
    """Dump the whole DB (pg_dump in the Postgres container) into a new SQL file."""
    return BackupResponse.from_backup(service.export_db())


@router.get("/admin/backups/{name}")
def download_backup(name: str, service: BackupService = Depends(backup_service)) -> Response:
    return Response(content=service.read_backup(name), media_type="application/sql")
