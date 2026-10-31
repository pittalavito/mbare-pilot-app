from time import perf_counter
from uuid import uuid4

from datapizza.tracing import ContextTracing

from core.error import AppError
from core.observability import LogPrefix, log_exception, observed
from domain.agent.base import Factory as AgentFactory
from domain.agent.masking import AgentMask
from domain.agent.tracing import Adapter as TracingAdapter
from models.domain.agent import AgentDefinition, AgentRunRecord, RunOrigin
from models.domain.chat import split_model_key
from models.domain.chatbot import ChatMessage
from service.agent_config_service import AgentConfigService
from service.chat_service import ChatService
from service.copilot_service import CopilotService
from service.git_service import GitService
from service.masking_service import MaskingService
from service.model_service import require_usable_model
from service.pipeline_service import PipelineService
from service.project_data_service import ProjectDataService
from service.store_service import StoreService
from tool.context import ToolContext
from tool.registry import build_tools


class AgentService:

    def __init__(
        self,
        chat_service: ChatService,
        agent_config_service: AgentConfigService,
        store_service: StoreService,
        git_service: GitService,
        pipeline_service: PipelineService,
        masking_service: MaskingService,
        project_data_service: ProjectDataService,
        copilot_service: CopilotService,
    ):
        """``pipeline_service`` lets the agents start automations (tool run_automation);
        ``masking_service`` hides the project's sensitive values from the LLM (a
        project without a map is left as it is);
        ``project_data_service`` lets them read the project's context (tool read_context);
        ``copilot_service`` lets the chatbot delegate agent tasks to Copilot (tool delegate_task).
        All are required: whether a tool may use one in a run is decided by the
        tool (``ToolContext.require_*``, the run's origin), not by leaving it out."""
        self._chat_service = chat_service
        self._agent_config_service = agent_config_service
        self._store_service = store_service
        self._git_service = git_service
        self._pipeline_service = pipeline_service
        self._masking_service = masking_service
        self._project_data_service = project_data_service
        self._copilot_service = copilot_service

    def run(self, config_name: str, task_input: str, *, project_name: str | None = None, origin: RunOrigin = RunOrigin.MANUAL,
            history: list[ChatMessage] | None = None) -> AgentRunRecord:
        """Run the agent configured as ``config_name`` (see ``run_definition``)."""
        definition = AgentDefinition.from_spec(self._agent_config_service.resolve(config_name))
        return self.run_definition(definition, task_input, project_name=project_name, origin=origin, history=history)

    @observed(LogPrefix.AGENT_SERVICE)
    def run_definition(self, definition: AgentDefinition, task_input: str, *, project_name: str | None = None,
                       origin: RunOrigin = RunOrigin.MANUAL, history: list[ChatMessage] | None = None) -> AgentRunRecord:
        """Run ``definition`` on ``task_input`` inside a datapizza trace and
        persist the run (facts + trace). A failed run is persisted too, with
        ``ok=False``. The run's project (``project_name``, else the
        definition's) is the one its tools work on; ``history`` are the
        previous messages of a conversation, oldest first. In a project with
        masking, the LLM sees aliases instead of the sensitive values: input,
        history and tool output are masked, the answer is unmasked."""
        project_name = project_name or definition.project_name
        require_usable_model(self._store_service, definition.model)
        client = self._chat_service.get_client(definition.model)
        session = self._masking_service.session(project_name) if project_name else None
        mask = AgentMask(session, self._repository_paths(project_name) if session else [])
        context = ToolContext(
            project_name=project_name,
            git=self._git_service,
            pipelines=self._pipeline_service,
            origin=origin,
            project_data=self._project_data_service,
            copilot=self._copilot_service,
        )
        tools = mask.wrap(build_tools(definition.tool_names, context))
        agent = AgentFactory.create_agent(definition, client, tools)
        prices = self._store_service.get_price_list()

        output, error = "", None
        start = perf_counter()
        with ContextTracing().trace(f"agent.{definition.name}") as current_trace:
            try:
                step = agent.run(mask.input(task_input), memory=AgentFactory.create_memory(mask.history(history)))
                output = mask.answer(step.text) if step else ""
            except AppError as exc:
                error = str(exc)
            except Exception as exc:
                log_exception(LogPrefix.AGENT_SERVICE, "Agent %s crashed", definition.name)
                error = str(exc)
            # Spans are discarded when the trace block exits: read them here.
            telemetry = TracingAdapter.to_run_telemetry(current_trace.get_spans(), prices)
        latency_ms = round((perf_counter() - start) * 1000, 1)

        record = AgentRunRecord(
            run_id=str(uuid4()),
            project_name=project_name,
            origin=origin,
            config_name=definition.name,
            role_name=definition.role_name,
            prompt_id=definition.prompt_id,
            prompt_version=definition.prompt_version,
            model=split_model_key(definition.model)[1],
            ok=error is None,
            error=error,
            latency_ms=latency_ms,
            input=task_input,
            output=output,
            telemetry=telemetry,
        )
        self._store_service.save_run(record)
        return record


    def _repository_paths(self, project_name: str) -> list[str]:
        """The project's repository paths, to be masked from the first message on.
        A project folder that is gone or unreadable has none."""
        try:
            return [repo.path for repo in self._git_service.repositories(project_name)]
        except AppError:
            return []
