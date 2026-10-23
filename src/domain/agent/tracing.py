"""Run telemetry from datapizza's own tracing.

datapizza emits an OpenTelemetry span for every agent (``type=agent``), tool
execution (``type=tool``, with arguments and result) and LLM call
(``type=generation``, with model and token usage). ``ContextTracing().trace()``
collects the spans of one run in memory; ``Adapter.to_run_telemetry`` turns
them into domain models. An LLM call nested under a tool span is billed to that
tool, every other call to the agent.

Read the spans INSIDE the ``trace()`` block: they are discarded on exit.
"""
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import StatusCode

from domain.chat.pricing import PriceList, compute_cost
from models.domain.agent import GenerationRecord, RunTelemetry, TokenSummary, ToolCallRecord

_TOOL_NAME_PREFIX = "Tool "


def _latency_ms(span: ReadableSpan) -> float:
    if span.start_time is None or span.end_time is None:
        return 0.0
    return round((span.end_time - span.start_time) / 1_000_000, 1)


def _tool_name(span: ReadableSpan) -> str:
    return span.name.removeprefix(_TOOL_NAME_PREFIX)


class Adapter:

    @staticmethod
    def to_run_telemetry(spans: list[ReadableSpan], prices: PriceList) -> RunTelemetry:
        by_id = {span.context.span_id: span for span in spans}
        ordered = sorted(spans, key=lambda span: span.start_time or 0)

        tool_calls: dict[int, ToolCallRecord] = {}
        for span in ordered:
            if span.attributes.get("type") == "tool":
                tool_calls[span.context.span_id] = Adapter.to_tool_call(span)

        telemetry = RunTelemetry()
        for span in ordered:
            if span.attributes.get("type") != "generation":
                continue
            tool_span = Adapter._enclosing_tool(span, by_id)
            generation = Adapter.to_generation(span, prices, tool_name=_tool_name(tool_span) if tool_span else None)
            telemetry.generations.append(generation)
            if tool_span is None:
                telemetry.agent_tokens += generation.tokens
            else:
                telemetry.tool_tokens += generation.tokens
                tool_call = tool_calls[tool_span.context.span_id]
                tool_call.tokens += generation.tokens

        telemetry.tool_calls = list(tool_calls.values())
        return telemetry

    @staticmethod
    def to_generation(span: ReadableSpan, prices: PriceList, tool_name: str | None = None) -> GenerationRecord:
        attributes = span.attributes
        model = str(attributes.get("model_name", "unknown"))
        input_tokens = int(attributes.get("prompt_tokens_used", 0) or 0)
        output_tokens = int(attributes.get("completion_tokens_used", 0) or 0)
        return GenerationRecord(
            model=model,
            tokens=TokenSummary(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached_tokens=int(attributes.get("cached_tokens_used", 0) or 0),
                thinking_tokens=int(attributes.get("thinking_tokens_used", 0) or 0),
                cost_eur=round(compute_cost(prices, model, input_tokens, output_tokens), 6),
            ),
            latency_ms=_latency_ms(span),
            tool_name=tool_name,
        )

    @staticmethod
    def to_tool_call(span: ReadableSpan) -> ToolCallRecord:
        failed = span.status.status_code == StatusCode.ERROR
        result = span.attributes.get("tool_result")
        return ToolCallRecord(
            name=_tool_name(span),
            arguments=str(span.attributes.get("tool_arguments", "")),
            result=str(result) if result is not None else None,
            ok=not failed,
            error=span.status.description if failed else None,
            latency_ms=_latency_ms(span),
        )

    @staticmethod
    def _enclosing_tool(span: ReadableSpan, by_id: dict[int, ReadableSpan]) -> ReadableSpan | None:
        """Nearest ancestor of type tool, or None."""
        parent = by_id.get(span.parent.span_id) if span.parent else None
        while parent is not None:
            if parent.attributes.get("type") == "tool":
                return parent
            parent = by_id.get(parent.parent.span_id) if parent.parent else None
        return None
