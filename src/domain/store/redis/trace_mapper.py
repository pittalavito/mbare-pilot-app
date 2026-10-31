"""Verbatim run traces: domain ``AgentRunRecord`` -> Redis ``AgentTraceRecord``
(read back as it is: the trace has no domain model of its own)."""
from models.domain.agent import AgentRunRecord
from models.store.redis import AgentTraceRecord


class Factory:
    """Write seam: domain models -> Redis records."""

    @staticmethod
    def to_trace_record(record: AgentRunRecord) -> AgentTraceRecord:
        return AgentTraceRecord(
            run_id=record.run_id,
            input=record.input,
            output=record.output,
            tool_calls=record.telemetry.tool_calls,
            generations=record.telemetry.generations,
        )
