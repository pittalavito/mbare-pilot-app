"""Roles and system prompt endpoints — /roles and /prompts. Roles and prompt
versions are never deleted: they are deactivated. Prompt versions are
immutable: saving a new text creates the next version."""
from fastapi import APIRouter, Depends, status

from controller.dependencies import agent_config_service
from models.controller.agent import (
    PromptCreateRequest,
    PromptResponse,
    PromptUpdateRequest,
    PromptVersionResponse,
    RoleCreateRequest,
    RoleResponse,
    RoleUpdateRequest,
)
from models.domain.agent import AgentRole
from service.agent_config_service import AgentConfigService

router = APIRouter(tags=["roles"])


@router.get("/roles")
def list_roles(project: str | None = None, include_global: bool = False,
               service: AgentConfigService = Depends(agent_config_service)) -> list[RoleResponse]:
    """The roles of ``project`` (optionally with the global ones), or the global ones."""
    return [RoleResponse.from_role(role) for role in service.list_roles(project, include_global=include_global)]


@router.post("/roles", status_code=status.HTTP_201_CREATED)
def create_role(request: RoleCreateRequest, service: AgentConfigService = Depends(agent_config_service)) -> RoleResponse:
    return RoleResponse.from_role(service.save_role(AgentRole(**request.model_dump()), create=True))


@router.patch("/roles/{name}")
def update_role(name: str, request: RoleUpdateRequest,
                service: AgentConfigService = Depends(agent_config_service)) -> RoleResponse:
    role = service.get_role(name)
    if request.description is not None:
        role = service.save_role(role.model_copy(update={"description": request.description}))
    if request.active is not None:
        role = service.set_role_active(name, request.active)
    return RoleResponse.from_role(role)


@router.get("/roles/{name}/prompts")
def list_prompt_versions(name: str, service: AgentConfigService = Depends(agent_config_service)) -> list[PromptResponse]:
    """Versions of the role's prompt, newest first."""
    service.get_role(name)  # 404 when absent
    return [PromptResponse.from_prompt(prompt) for prompt in service.list_prompts(name)]


@router.post("/roles/{name}/prompts")
def create_prompt_version(name: str, request: PromptCreateRequest,
                          service: AgentConfigService = Depends(agent_config_service)) -> PromptVersionResponse:
    """New version of the role's prompt; an identical text returns the latest one (``created`` False)."""
    service.get_role(name)
    latest = service.latest_prompt(name)
    prompt = service.create_prompt_version(name, request.text)
    created = latest is None or prompt.id != latest.id
    return PromptVersionResponse(prompt=PromptResponse.from_prompt(prompt), created=created)


@router.patch("/prompts/{prompt_id}")
def update_prompt(prompt_id: int, request: PromptUpdateRequest,
                  service: AgentConfigService = Depends(agent_config_service)) -> PromptResponse:
    """Activate or deactivate a version (its text never changes)."""
    return PromptResponse.from_prompt(service.set_prompt_active(prompt_id, request.active))
