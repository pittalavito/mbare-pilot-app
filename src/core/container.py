"""Composition root: builds every dependency once per process (API, worker;
UI never: it talks to the API). Nothing else builds services."""
import sys

import datapizza.tracing

from config import Config
from core.observability import LogPrefix, observed
from domain.chat.models_default import DEFAULT_CHAT_MODELS
from domain.client.embedding.embedder import Factory as EmbedderFactory
from domain.process.manager import ProcessManager
from domain.project.folder_browser import FolderBrowser
from service.agent_config_service import AgentConfigService
from service.agent_service import AgentService
from service.atlassian_service import AtlassianService
from service.automation_cache_service import AutomationCacheService
from service.backup_service import BackupService
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
from service.run_service import RunService
from service.store.stores import Stores


class Container:

    @observed(LogPrefix.CONTAINER)
    def __init__(self, stores: Stores | None = None):
        """``stores`` is for tests (in-memory backends); by default they
        connect to Postgres and Redis from the Config."""
        config = Config.get()
        datapizza.tracing.console.quiet = not config.datapizza_trace_summary

        stores = stores or Stores()
        self.store_service = stores.store_service
        self.chat_service = ChatService()
        self.run_service = RunService(stores.runs)
        self.model_service = ModelService(catalog=stores.catalog)
        self.agent_config_service = AgentConfigService(store_service=self.store_service, catalog=stores.catalog)
        self.project_data_service = ProjectDataService(store_service=self.store_service)
        self.atlassian_service = AtlassianService(store_service=self.store_service, project_data_service=self.project_data_service)
        self.git_service = GitService(store_service=self.store_service)
        self.masking_service = MaskingService(store_service=self.store_service, masks=stores.masks)
        self.pipeline_service = PipelineService(
            store_service=self.store_service, workers=stores.workers, catalog=stores.catalog,
            agent_config_service=self.agent_config_service,
        )
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
            runs=stores.runs,
            catalog=stores.catalog,
            git_service=self.git_service,
            pipeline_service=self.pipeline_service,
            masking_service=self.masking_service,
            project_data_service=self.project_data_service,
            copilot_service=self.copilot_service,
        )
        self.automation_cache_service = AutomationCacheService(
            store_service=self.store_service,
            pipeline_service=self.pipeline_service,
            embedder=EmbedderFactory.create(config.automation_cache_embedder),
            threshold=config.automation_cache_threshold,
            masking_service=self.masking_service,
        )
        self.chatbot_service = ChatbotService(
            store_service=self.store_service,
            catalog=stores.catalog,
            agent_config_service=self.agent_config_service,
            agent_service=self.agent_service,
            automation_cache=self.automation_cache_service,
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
            masks=stores.masks,
            folder_browser=FolderBrowser(config.project_root_paths),
            definition_service=self.definition_service,
        )

        self._seed_defaults()

    def _seed_defaults(self) -> None:
        """At startup, what is missing: the default models, the tool catalog and
        the global agents of definition/global-agent.yml (edits made from the UI
        are never overwritten) and the default chatbots each project misses.
        Models first: agents and chatbots need them."""
        self.model_service.seed_defaults(DEFAULT_CHAT_MODELS)
        self.agent_config_service.sync_tools()
        self.definition_service.seed_global_agents()
        self.definition_service.seed_default_chatbots([project.name for project in self.store_service.list_projects()])
