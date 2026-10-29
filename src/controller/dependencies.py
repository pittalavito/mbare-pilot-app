"""Dependency providers for the API routers: the services of the Container
built at startup (``app.state.container``). Use with ``Depends(...)``."""
from fastapi import Request

from service.agent_config_service import AgentConfigService
from service.atlassian_service import AtlassianService
from service.backup_service import BackupService
from service.automation_cache_service import AutomationCacheService
from service.chatbot_service import ChatbotService
from service.copilot_service import CopilotService
from service.definition_service import DefinitionService
from service.process_service import ProcessService
from service.git_service import GitService
from service.masking_service import MaskingService
from service.model_service import ModelService
from service.pipeline_service import PipelineService
from service.project_data_service import ProjectDataService
from service.project_service import ProjectService
from service.store_service import StoreService


def project_service(request: Request) -> ProjectService:
    return request.app.state.container.project_service


def agent_config_service(request: Request) -> AgentConfigService:
    return request.app.state.container.agent_config_service


def model_service(request: Request) -> ModelService:
    return request.app.state.container.model_service


def chatbot_service(request: Request) -> ChatbotService:
    return request.app.state.container.chatbot_service


def automation_cache_service(request: Request) -> AutomationCacheService:
    return request.app.state.container.automation_cache_service


def definition_service(request: Request) -> DefinitionService:
    return request.app.state.container.definition_service


def project_data_service(request: Request) -> ProjectDataService:
    return request.app.state.container.project_data_service


def git_service(request: Request) -> GitService:
    return request.app.state.container.git_service


def pipeline_service(request: Request) -> PipelineService:
    return request.app.state.container.pipeline_service


def atlassian_service(request: Request) -> AtlassianService:
    return request.app.state.container.atlassian_service


def store_service(request: Request) -> StoreService:
    return request.app.state.container.store_service


def backup_service(request: Request) -> BackupService:
    return request.app.state.container.backup_service


def masking_service(request: Request) -> MaskingService:
    return request.app.state.container.masking_service


def process_service(request: Request) -> ProcessService:
    return request.app.state.container.process_service


def copilot_service(request: Request) -> CopilotService:
    return request.app.state.container.copilot_service
