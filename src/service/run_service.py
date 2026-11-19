"""Observability of the agents' runs (Admin → Osservabilità): what ran, with
which tokens and costs, and the verbatim trace of one run. Read-only: the runs
are written by AgentService as they end."""
import json

from core.error import NotFoundError
from domain.masking.masker import Masker
from models.domain.agent import AgentRunSummary, ModelMessage, ToolCallSummary
from models.domain.transcript import RunTranscript, TranscriptTool, TranscriptView
from models.store.redis import AgentTraceRecord
from service.masking_service import MaskingService
from service.store.run_store import RunStore


class RunService:

    def __init__(self, runs: RunStore, masking: MaskingService | None = None):
        self._runs = runs
        self._masking = masking

    def list_runs(self, limit: int = 100) -> list[AgentRunSummary]:
        """Newest first."""
        return self._runs.list_runs(limit)

    def list_tool_calls(self, limit: int = 100) -> list[ToolCallSummary]:
        """Newest first."""
        return self._runs.list_tool_calls(limit)

    def trace(self, run_id: str) -> AgentTraceRecord:
        """Input, output, tool calls and LLM generations, as recorded."""
        trace = self._runs.get_trace(run_id)
        if trace is None:
            raise NotFoundError(f"Trace non trovato: {run_id}")
        return trace

    def transcript(self, run_id: str) -> RunTranscript:
        """«🔍 Cosa ha visto il modello» (plan 29): the exchange as it went (masked) and in clear (the project's map
        applied back; input and output are the run's own clear ones)."""
        trace = self.trace(run_id)
        if trace.transcript is None:
            raise NotFoundError("Questa esecuzione non ha la trascrizione (registrata prima del piano 29).")
        recorded = trace.transcript
        tools = [TranscriptTool(name=call.name, arguments=_pretty(call.arguments), result=_pretty(call.result or ""), error=call.error)
                 for call in trace.tool_calls]
        masked = TranscriptView(system_prompt=recorded.system_prompt, history=recorded.history, input=recorded.input,
                                tool_calls=tools, output=_pretty(recorded.output))
        entries = self._masking.entries(trace.project_name) if self._masking and trace.project_name else []
        clear_text = Masker(entries).unmask if entries else (lambda text: text)
        clear = TranscriptView(
            system_prompt=clear_text(recorded.system_prompt),
            history=[ModelMessage(role=message.role, content=clear_text(message.content)) for message in recorded.history],
            input=trace.input or clear_text(recorded.input),
            tool_calls=[tool.model_copy(update={"arguments": clear_text(tool.arguments), "result": clear_text(tool.result),
                                                "error": clear_text(tool.error) if tool.error else None}) for tool in tools],
            output=_pretty(trace.output) if trace.output else clear_text(masked.output),
        )
        return RunTranscript(run_id=run_id, project_name=trace.project_name, masked=masked, clear=clear,
                             aliases=sorted({entry.alias for entry in entries}))


def _pretty(text: str) -> str:
    """A JSON text indented (to read it); anything else as it is."""
    stripped = text.strip()
    if stripped[:1] in "{[":
        try:
            return json.dumps(json.loads(stripped), ensure_ascii=False, indent=2)
        except ValueError:
            return text
    return text
