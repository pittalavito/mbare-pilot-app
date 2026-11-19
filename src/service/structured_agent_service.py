"""The agents of the Library with a structured answer (``output:``, plan 17):
**one call**, no tools, the schema of ``STRUCTURED_OUTPUTS``; a service may
give it tools (the Pianificatore's ``search_context``, plan 26): then a few
steps (``max_steps``) of tool calls before the structured answer. The services
(«Elabora WIP», the Pianificatore, «📎 Da riferimenti») prepare and mask the
input, call the agent by name, use the answer and record the run with what
they made of it."""
from dataclasses import dataclass
from time import perf_counter
from uuid import uuid4

from datapizza.agents import Agent
from datapizza.tools import Tool
from datapizza.tracing import ContextTracing
from pydantic import BaseModel

from core.error import ValidationError
from core.observability import LogPrefix, log_exception
from domain.agent.outputs import STRUCTURED_OUTPUTS
from domain.agent.tracing import Adapter as TracingAdapter
from models.domain.agent import AgentDefinition, AgentRunRecord, ModelTranscript, RunOrigin, RunTelemetry
from models.domain.chat import split_model_key
from service.agent_config_service import AgentConfigService
from service.chat_service import ChatService
from service.model_service import require_usable_model
from service.store.catalog_store import CatalogStore
from service.store.run_store import RunStore


@dataclass
class StructuredCall:
    agent: AgentDefinition
    answer: BaseModel | None
    """None when the call failed."""
    error: str | None
    telemetry: RunTelemetry
    latency_ms: float
    transcript: ModelTranscript | None = None
    """What went to and came from the model, masked (plan 29)."""


class StructuredAgentService:

    def __init__(self, agents: AgentConfigService, chat: ChatService, catalog: CatalogStore, runs: RunStore):
        self._agents = agents
        self._chat = chat
        self._catalog = catalog
        self._runs = runs

    def agent(self, name: str, output: str) -> AgentDefinition:
        """The agent ``name`` (global-agent.yml), which must answer with ``output``."""
        agent = AgentDefinition.from_spec(self._agents.resolve(name))
        if agent.output != output:
            raise ValidationError(f"L'agente {name} deve avere «output: {output}» in global-agent.yml.")
        return agent

    def call(self, agent: AgentDefinition, text: str, tools: list[Tool] | None = None) -> StructuredCall:
        """One structured call of ``agent`` on ``text`` (already masked); a failure is in ``error``.
        With ``tools``: up to ``agent.max_steps`` steps, the tools' calls then the structured answer."""
        require_usable_model(self._catalog, agent.model)
        client = self._chat.get_client(agent.model)
        schema = STRUCTURED_OUTPUTS[agent.output]
        answer, error = None, None
        start = perf_counter()
        with ContextTracing().trace(f"agent.{agent.name}") as current_trace:
            try:
                if tools:
                    runner = Agent(name=agent.name, client=client, system_prompt=agent.system_prompt, tools=tools,
                                   max_steps=max(2, agent.max_steps), output_cls=schema)
                    response = runner.run(text)
                else:
                    response = client.structured_response(input=text, output_cls=schema, system_prompt=agent.system_prompt)
                if response is None or not response.structured_data:
                    raise ValueError("nessuna risposta strutturata")
                data = response.structured_data[0]
                answer = schema.model_validate(data.model_dump() if hasattr(data, "model_dump") else data)
            except Exception as exc:  # noqa: BLE001 - any failure of the call is recorded and reported
                log_exception(LogPrefix.AGENT_SERVICE, "Agente %s fallito", agent.name)
                error = str(exc) or type(exc).__name__
            telemetry = TracingAdapter.to_run_telemetry(current_trace.get_spans(), self._catalog.price_list())
        masked_output = answer.model_dump_json(indent=2) if answer is not None else ""
        return StructuredCall(agent=agent, answer=answer, error=error, telemetry=telemetry,
                              latency_ms=round((perf_counter() - start) * 1000, 1),
                              transcript=ModelTranscript(system_prompt=agent.system_prompt, input=text, output=masked_output))

    def save(self, call: StructuredCall, *, project_name: str, origin: RunOrigin, input: str, output: str) -> str:
        """The call as an agent run (``input`` and ``output`` in clear); its id."""
        run_id = str(uuid4())
        agent = call.agent
        self._runs.save(AgentRunRecord(
            run_id=run_id, project_name=project_name, origin=origin, config_name=agent.name, role_name=agent.role_name,
            prompt_id=agent.prompt_id, prompt_version=agent.prompt_version, model=split_model_key(agent.model)[1],
            ok=call.error is None, error=call.error, latency_ms=call.latency_ms, input=input, output=output, telemetry=call.telemetry,
            transcript=call.transcript,
        ))
        return run_id
