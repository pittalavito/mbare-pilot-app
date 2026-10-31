"""Catalogs: the tools (/tools, read-only), the models the forms pick from
(/models/choices) and the whole model catalog edited in Admin (/models)."""
from fastapi import APIRouter, Depends

from controller.dependencies import agent_config_service, model_service
from models.controller.admin import CatalogModelBody
from models.controller.agent import ModelChoicesResponse, ToolResponse
from service.agent_config_service import AgentConfigService
from service.model_service import ModelService

router = APIRouter(tags=["catalogs"])


@router.get("/tools")
def list_tools(service: AgentConfigService = Depends(agent_config_service)) -> list[ToolResponse]:
    """The tool catalog; ``available`` False = catalogued but no longer implemented."""
    return [ToolResponse.from_tool(tool) for tool in service.list_tools()]


@router.get("/models/choices")
def model_choices(current: str | None = None, service: ModelService = Depends(model_service)) -> ModelChoicesResponse:
    """Model keys for a picker (``provider/model``), keeping ``current`` visible."""
    usable = [model.key for model in service.list_models(active_only=True)]
    return ModelChoicesResponse(choices=service.choices(current), usable=usable)


@router.get("/models")
def list_models(service: ModelService = Depends(model_service)) -> list[CatalogModelBody]:
    in_use = service.keys_in_use()
    return [CatalogModelBody.from_model(model, model.key in in_use) for model in service.list_models()]


@router.put("/models")
def save_models(request: list[CatalogModelBody], service: ModelService = Depends(model_service)) -> list[CatalogModelBody]:
    """Make the body the whole catalog. A model in use cannot be removed (409)."""
    service.save_catalog([model.to_model() for model in request])
    return list_models(service)
