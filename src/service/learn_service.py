"""From an Operator's run to an automation (plan 11), without an LLM: the
successful calls of the Operator's tools, in order, become ``tool`` steps with
the real values (the trace has the aliases the agent saw: unmasked here). The
values that change from a time to the next (branch, base, task) are proposed as
fields from the arguments' names; the user corrects them and saves. The run's
trace expires (Redis): then there is nothing left to promote."""
import ast
import json
from typing import Any

from core.error import NotFoundError, ValidationError
from models.domain.chatbot import READ_ONLY_TOOLS, STEP_TOOLS
from models.domain.learn import LearnDraft, LearnedStep, LearnedValue, LearnRequest
from models.domain.pipeline import Pipeline, PipelineStep, StepKind
from models.store.redis import AgentTraceRecord
from service.masking_service import MaskingService
from service.pipeline_service import PipelineService
from service.store.chatbot_store import ChatbotStore
from service.store.run_store import RunStore

FIELD_OF_ARGUMENT = {"branch": "branch", "name": "branch", "start_point": "base"}
"""The tools' arguments whose value is usually different every time, and the field proposed for it."""
EXPIRED = "La traccia di questa risposta è scaduta: non so più cosa ha fatto l'agente. Ripeti la richiesta e promuovi la nuova."


class LearnService:

    def __init__(self, chatbots: ChatbotStore, runs: RunStore, masking: MaskingService, pipelines: PipelineService):
        self._chatbots = chatbots
        self._runs = runs
        self._masking = masking
        self._pipelines = pipelines

    def draft(self, message_id: int) -> LearnDraft:
        """The draft of an automation from the run of an assistant message."""
        message = self._chatbots.get_message(message_id)
        if message is None:
            raise NotFoundError(f"Messaggio non trovato: {message_id}")
        conversation = self._chatbots.get_conversation(message.conversation_id)
        chatbot = self._chatbots.get_chatbot(conversation.chatbot_id) if conversation else None
        if conversation is None or chatbot is None:
            raise NotFoundError(f"Messaggio non trovato: {message_id}")
        trace = self._runs.get_trace(message.run_id) if message.run_id else None
        if trace is None:
            raise NotFoundError(EXPIRED)
        session = self._masking.session(chatbot.project_name)
        steps = [LearnedStep(tool=call.name, args=session.unmask_value(args), read_only=call.name in READ_ONLY_TOOLS)
                 for call, args in _successful_calls(trace)]
        if not any(not step.read_only for step in steps):
            raise ValidationError("In questa risposta l'agente non ha fatto azioni riuscite da ripetere: niente da salvare.")
        return LearnDraft(run_id=trace.run_id, steps=steps, values=_values(steps, conversation.context),
                          cost_eur=round(sum(generation.tokens.cost_eur for generation in trace.generations), 6))

    def save(self, project_name: str, request: LearnRequest) -> Pipeline:
        """The automation: one ``tool`` step per call kept, the values chosen as fields replaced by ``{in:field}``."""
        unknown = [step.tool for step in request.steps if step.tool not in STEP_TOOLS]
        if unknown:
            raise ValidationError(f"Tool che non si possono ripetere in un'automation: {', '.join(unknown)}.")
        fields = {value: field for value, field in request.fields.items() if value and field}
        steps = [PipelineStep(name=f"{position}. {step.tool}", kind=StepKind.TOOL, tool_name=step.tool, params=_with_fields(step.args, fields))
                 for position, step in enumerate(request.steps, start=1)]
        return self._pipelines.create_pipeline(project_name, request.name, description=request.description, steps=steps,
                                               fields=list(dict.fromkeys(fields.values())), purpose=request.purpose)


def _successful_calls(trace: AgentTraceRecord) -> list[tuple[Any, dict[str, Any]]]:
    """The calls of the steps' tools that worked (no exception, no ``error`` in the result), with their arguments."""
    calls = []
    for call in trace.tool_calls:
        if not call.ok or call.name not in STEP_TOOLS:
            continue
        try:
            result = json.loads(call.result or "{}")
            args = ast.literal_eval(call.arguments or "{}")
        except (ValueError, SyntaxError):
            continue
        if isinstance(result, dict) and result.get("error"):
            continue
        if isinstance(args, dict):
            calls.append((call, args))
    return calls


def _values(steps: list[LearnedStep], context: str) -> list[LearnedValue]:
    """Every string argument once, with the field proposed for it (``task`` for the note the conversation is about)."""
    found: dict[str, str] = {}
    for step in steps:
        for key, value in step.args.items():
            if not isinstance(value, str) or not value.strip() or key == "command":
                continue
            field = "task" if context and value == context else FIELD_OF_ARGUMENT.get(key, "")
            if value not in found or (field and not found[value]):
                found[value] = field
    return [LearnedValue(value=value, field=field) for value, field in found.items()]


def _with_fields(value: Any, fields: dict[str, str]) -> Any:
    if isinstance(value, str):
        return f"{{in:{fields[value]}}}" if value in fields else value
    if isinstance(value, dict):
        return {key: _with_fields(item, fields) for key, item in value.items()}
    if isinstance(value, list):
        return [_with_fields(item, fields) for item in value]
    return value
