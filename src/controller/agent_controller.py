"""Agents endpoints — everything under /agents. ``?project=<name>`` selects a
project's agents; without it, the global ones (Library)."""
from fastapi import APIRouter, Depends, Response, status

from core.error import NotFoundError
from controller.dependencies import agent_config_service
from service.agent_config_service import AgentConfigService
from models.controller.agent import AgentCreateRequest, AgentResponse, AgentUpdateRequest
from models.domain.agent import AgentConfig

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("")
def list_agents(project: str | None = None, include_global: bool = False, service: AgentConfigService = Depends(agent_config_service)) -> list[AgentResponse]:
    """The agents of ``project`` (optionally with the global ones), or the global ones."""
    return _responses(service, service.list_configs(project, include_global=include_global))


@router.get("/{name}")
def get_agent(name: str, service: AgentConfigService = Depends(agent_config_service)) -> AgentResponse:
    return _responses(service, [service.get_config(name)])[0]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_agent(request: AgentCreateRequest, service: AgentConfigService = Depends(agent_config_service)) -> AgentResponse:
    config = service.save_config(AgentConfig(**request.model_dump()), create=True)
    return _responses(service, [config])[0]


@router.put("/{name}")
def update_agent(name: str, request: AgentUpdateRequest, service: AgentConfigService = Depends(agent_config_service)) -> AgentResponse:
    current = service.get_config(name)  # 404 when absent; name and scope stay
    config = service.save_config(AgentConfig(name=name, project_name=current.project_name, **request.model_dump()))
    return _responses(service, [config])[0]


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(name: str, service: AgentConfigService = Depends(agent_config_service)) -> Response:
    """Past runs of the agent stay in Observability."""
    if not service.delete_config(name):
        raise NotFoundError(f"Configurazione agente non trovata: {name}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _responses(service: AgentConfigService, configs: list[AgentConfig]) -> list[AgentResponse]:
    versions = {prompt.id: prompt.version for prompt in service.list_prompts()}
    return [
        AgentResponse.from_config(config, versions.get(config.prompt_id), service.blocked_reason(config))
        for config in configs
    ]
