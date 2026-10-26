"""The usage file Copilot CLI writes with ``--usage-output-file``: the
accounting of the whole Copilot session so far (cumulative across resumed
turns, as the ``accountingSnapshot`` of its session state). Read tolerantly:
missing fields count as zero, an unreadable file as no usage."""
import json
from pathlib import Path

from models.domain.copilot import CopilotUsage


def read_usage(path: Path) -> tuple[CopilotUsage | None, str]:
    """The session's totals and the model Copilot used last; ``(None, "")``
    when the file is missing or not JSON (Copilot killed before writing it)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, ""
    if not isinstance(data, dict):
        return None, ""
    tokens = {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0, "reasoning_tokens": 0}
    for metrics in (data.get("modelMetrics") or {}).values():
        usage = (metrics or {}).get("usage") or {}
        tokens["input_tokens"] += _int(usage.get("inputTokens"))
        tokens["output_tokens"] += _int(usage.get("outputTokens"))
        tokens["cache_read_tokens"] += _int(usage.get("cacheReadTokens"))
        tokens["cache_write_tokens"] += _int(usage.get("cacheWriteTokens"))
        tokens["reasoning_tokens"] += _int(usage.get("reasoningTokens"))
    usage = CopilotUsage(
        premium_requests=_float(data.get("totalPremiumRequestCost")),
        nano_aiu=_int(data.get("totalNanoAiu")),
        api_duration_ms=_int(data.get("totalApiDurationMs")),
        **tokens,
    )
    return usage, str(data.get("currentModel") or "")


def _int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
