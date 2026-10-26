"""Composition root: builds every dependency once per process (API, worker;
UI never: it talks to the API). Nothing else builds services."""
import sys

import datapizza.tracing

from config import Config
from core.observability import LogPrefix, configure_logging, observed

from domain.chat.models_default import DEFAULT_CHAT_MODELS
from domain.client.embedding.embedder import Factory as EmbedderFactory
from domain.process.manager import ProcessManager
from domain.project.folder_browser import FolderBrowser

from service.agent_config_service import AgentConfigService
from service.agent_service import AgentService
from service.atlassian_service import AtlassianService
from service.backup_service import BackupService
from service.chat_route_service import ChatRouteService
from service.chat_service import ChatService
from service.chatbot_service import ChatbotService
from service.copilot_service import CopilotService
from service.definition_service import DefinitionService
from service.git_service import GitService
from service.masking_service import MaskingService
from service.model_service import ModelService
from service.pipeline_runner import PipelineRunner
from service.pipeline_service import PipelineService
from service.process_service import ProcessService
from service.project_data_service import ProjectDataService
from service.project_service import ProjectService
from service.store_service import StoreService


class Container:

    @observed(LogPrefix.CONTAINER)
    def __init__(self, store_service: StoreService | None = None):
        """``store_service`` is for tests (in-memory backends); by default it
        connects to Postgres and Redis from the Config."""
        config = Config.get()
        datapizza.tracing.console.quiet = not config.datapizza_trace_summary

        self.store_service = store_service or StoreService()
        self.chat_service = ChatService()
        self.model_service = ModelService(store_service=self.store_service)
        self.agent_config_service = AgentConfigService(store_service=self.store_service)
        self.project_data_service = ProjectDataService(store_service=self.store_service)
        self.atlassian_service = AtlassianService(store_service=self.store_service)
        self.git_service = GitService(store_service=self.store_service)
        self.masking_service = MaskingService(store_service=self.store_service)
        self.pipeline_service = PipelineService(store_service=self.store_service, agent_config_service=self.agent_config_service)
        self.process_service = ProcessService(
            pipeline_service=self.pipeline_service,
            manager=ProcessManager(cwd=config.app_root, run_dir=config.run_dir, log_dir=config.logs_dir),
            worker_command=[sys.executable, config.worker_script],
        )
        self.backup_service = BackupService.from_config()
        self.copilot_service = CopilotService.from_config(
            store_service=self.store_service,
            git_service=self.git_service,
            project_data_service=self.project_data_service,
        )
        self.agent_service = AgentService(
            chat_service=self.chat_service,
            agent_config_service=self.agent_config_service,
            store_service=self.store_service,
            git_service=self.git_service,
            pipeline_service=self.pipeline_service,
            masking_service=self.masking_service,
            project_data_service=self.project_data_service,
            copilot_service=self.copilot_service,
        )
        self.chat_route_service = ChatRouteService(
            store_service=self.store_service,
            pipeline_service=self.pipeline_service,
            embedder=EmbedderFactory.create(config.chat_route_embedder),
            threshold=config.chat_route_threshold,
            masking_service=self.masking_service,
        )
        self.chatbot_service = ChatbotService(
            store_service=self.store_service,
            agent_config_service=self.agent_config_service,
            agent_service=self.agent_service,
            route_service=self.chat_route_service,
        )
        self.definition_service = DefinitionService(
            store_service=self.store_service,
            agent_config_service=self.agent_config_service,
            chatbot_service=self.chatbot_service,
            pipeline_service=self.pipeline_service,
        )
        self.pipeline_runner = PipelineRunner(
            store_service=self.store_service,
            agent_service=self.agent_service,
            git_service=self.git_service,
            project_data_service=self.project_data_service,
            masking_service=self.masking_service,
        )
        self.project_service = ProjectService(
            store_service=self.store_service,
            folder_browser=FolderBrowser(config.project_root_paths),
        )

        self._seed_defaults()

    def _seed_defaults(self) -> None:
        """At startup, what is missing: the default models, the tool catalog and
        the global agents of definition/global-agent.yml (edits made from the UI
        are never overwritten). Models first: agents need them."""
        self.model_service.seed_defaults(DEFAULT_CHAT_MODELS)
        self.agent_config_service.sync_tools()
        self.definition_service.seed_global_agents()
