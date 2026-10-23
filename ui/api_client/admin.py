"""Admin endpoints, typed: app config, observability, model catalog."""
from typing import Any

from api_client.http import ApiClient, segment
from api_client.models import AppConfig, CatalogModel, RunSummary, ToolCall


class AdminApi:

    def __init__(self, client: ApiClient):
        self._client = client

    def config(self) -> AppConfig:
        return AppConfig.model_validate(self._client.get("/admin/config"))

    def runs(self) -> list[RunSummary]:
        """Newest first."""
        return [RunSummary.model_validate(item) for item in self._client.get("/observability/runs")]

    def trace(self, run_id: str) -> dict[str, Any]:
        return self._client.get(f"/observability/runs/{segment(run_id)}/trace")

    def tool_calls(self) -> list[ToolCall]:
        return [ToolCall.model_validate(item) for item in self._client.get("/observability/tool-calls")]

    def models(self) -> list[CatalogModel]:
        return [CatalogModel.model_validate(item) for item in self._client.get("/models")]

    def save_models(self, models: list[CatalogModel]) -> list[CatalogModel]:
        """``models`` becomes the whole catalog."""
        saved = self._client.put("/models", json=[model.model_dump() for model in models])
        return [CatalogModel.model_validate(item) for item in saved]
