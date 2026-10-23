"""Admin endpoints: the app config with secrets masked (/admin/config) and the
observability facts (/observability/...: runs and tool calls from Postgres,
the verbatim trace of a run from Redis)."""
from typing import Any

from fastapi import APIRouter, Depends

from config import Config
from controller.dependencies import store_service
from core.error import NotFoundError
from models.controller.admin import ConfigResponse, RunSummaryResponse, ToolCallResponse
from service.store_service import StoreService

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
