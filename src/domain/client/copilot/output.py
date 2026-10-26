"""Copilot's JSONL output (``--output-format json``) as a ``CopilotTurn``: the
answer is the last ``assistant.message`` with content, the ``result`` event has
exit code and usage."""
import json

from domain.client.copilot.process import ProcessResult, StopReason
from models.domain.copilot import CopilotTurn

_ERROR_TAIL = 1500


def to_turn(result: ProcessResult, timeout_seconds: float) -> CopilotTurn:
    message, summary = "", None
    for line in result.stdout:
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "assistant.message" and (content := (event.get("data") or {}).get("content")):
            message = content
        elif event.get("type") == "result":
            summary = event
    exit_code = summary.get("exitCode", result.returncode) if summary else result.returncode
    turn = CopilotTurn(message=message, exit_code=exit_code, premium_requests=int(((summary or {}).get("usage") or {}).get("premiumRequests") or 0))
    if result.stopped == StopReason.CANCELLED:
        return turn.model_copy(update={"error": "Annullata.", "cancelled": True})
    if result.stopped == StopReason.TIMEOUT:
        return turn.model_copy(update={"error": f"Nessuna risposta entro {timeout_seconds / 60:.0f} minuti: fermata."})
    if exit_code != 0:
        detail = result.stderr.strip()[-_ERROR_TAIL:] or f"exit code {exit_code}"
        return turn.model_copy(update={"error": f"Copilot CLI ha dato errore: {detail}"})
    return turn
