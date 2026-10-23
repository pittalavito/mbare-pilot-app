from time import perf_counter
from uuid import uuid4

from datapizza.tracing import ContextTracing

from core.error import AppError
from models.domain.masking import MaskCategory
from core.observability import LogPrefix, log_exception, observed
from domain.agent.base import Factory as AgentFactory
from domain.agent.tracing import Adapter as TracingAdapter
from models.domain.agent import AgentConfig, AgentDefinition, AgentRunRecord, RunOrigin
from models.domain.chat import split_model_key
from models.domain.chatbot import ChatMessage
from service.agent_config_service import AgentConfigService
from service.chat_service import ChatService
from service.git_service import GitService
from service.masking_service import MaskingService
from service.model_service import require_usable_model
from service.pipeline_service import PipelineService
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
        pipeline_service: PipelineService | None = None,
        masking_service: MaskingService | None = None,
    ):
        """``pipeline_service`` lets the agents start automations (tool run_automation);
        ``masking_service`` hides the project's sensitive values from the LLM."""
        self._chat_service = chat_service
        self._agent_config_service = agent_config_service
        self._store_service = store_service
        self._git_service = git_service
        self._pipeline_service = pipeline_service
        self._masking_service = masking_service

    def run(self, config_name: str, task_input: str, *, project_name: str | None = None,
            origin: RunOrigin = RunOrigin.MANUAL, history: list[ChatMessage] | None = None,
            depth: int = 0) -> AgentRunRecord:
        """Run the agent configured as ``config_name`` (see ``run_definition``)."""
        definition = AgentDefinition.from_spec(self._agent_config_service.resolve(config_name))
        return self.run_definition(definition, task_input, project_name=project_name, origin=origin, history=history,
                                   depth=depth)

    def delegable_agents(self, project_name: str | None) -> list[AgentConfig]:
        """The agents another agent can delegate to (tool ask_agent): the
        project's and the global ones (only the global ones outside a project),
        those that can run right now."""
        configs = self._agent_config_service.list_configs(project_name, include_global=True)
        return [config for config in configs if self._agent_config_service.blocked_reason(config) is None]

    def delegate(self, config_name: str, question: str, *, project_name: str | None, depth: int) -> AgentRunRecord:
        """Run ``config_name`` on behalf of another agent, on the same project."""
        return self.run(config_name, question, project_name=project_name, origin=RunOrigin.AGENT, depth=depth)

    @observed(LogPrefix.AGENT_SERVICE)
    def run_definition(self, definition: AgentDefinition, task_input: str, *, project_name: str | None = None,
                       origin: RunOrigin = RunOrigin.MANUAL, history: list[ChatMessage] | None = None,
                       depth: int = 0) -> AgentRunRecord:
        """Run ``definition`` on ``task_input`` inside a datapizza trace and
        persist the run (facts + trace). A failed run is persisted too, with
        ``ok=False``. The run's project (``project_name``, else the
        definition's) is the one its tools work on; ``history`` are the
        previous messages of a conversation, oldest first; ``depth`` the
        delegation level (0 unless asked by another agent). In a project with
        masking, the LLM sees aliases instead of the sensitive values: input,
        history and tool output are masked, the answer is unmasked."""
        project_name = project_name or definition.project_name
        require_usable_model(self._store_service, definition.model)
        client = self._chat_service.get_client(definition.model)
        mask = self._masking_service.session(project_name) if self._masking_service and project_name else None
        if mask:
            self._register_repositories(mask, project_name)
        context = ToolContext(
            project_name=project_name, git=self._git_service, agents=self, depth=depth,
            pipelines=self._pipeline_service, origin=origin, mask=mask,
        )
        tools = build_tools(definition.tool_names, context)
        agent = AgentFactory.create_agent(definition, client, tools)
        prices = self._store_service.get_price_list()

        output, error = "", None
        start = perf_counter()
        with ContextTracing().trace(f"agent.{definition.name}") as current_trace:
            try:
                step = agent.run(_masked_text(mask, task_input), memory=AgentFactory.create_memory(_masked_history(mask, history)))
                output = mask.unmask(step.text) if mask and step else (step.text if step else "")
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


    def _register_repositories(self, mask, project_name: str) -> None:
        """The project's repository names are masked from the first message on,
        not only after a tool reads them. A project folder that is gone or
        unreadable just registers nothing."""
        try:
            repositories = self._git_service.repositories(project_name)
        except AppError:
            return
        mask.register_all(MaskCategory.REPOSITORY, [repo.path for repo in repositories])


def _masked_text(mask, text: str) -> str:
    return mask.mask(text) if mask else text


def _masked_history(mask, history: list[ChatMessage] | None) -> list[ChatMessage]:
    if not mask:
        return history or []
    return [message.model_copy(update={"content": mask.mask(message.content)}) for message in history or []]
