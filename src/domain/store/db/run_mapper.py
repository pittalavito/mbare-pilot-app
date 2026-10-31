"""Agent runs: domain run records <-> ``agent_run`` / ``tool_call`` rows.

``Adapter`` (rows -> domain models, reads) and ``Factory`` (domain models ->
rows, writes) are the translation seams of the runs' repository."""
from domain.store.db.mapper import as_utc
from models.domain.agent import AgentRunRecord, AgentRunSummary, TokenSummary, ToolCallSummary
from models.store.db import AgentRunTable, ToolCallTable


class Adapter:
    """Read seam: DB rows -> domain models."""

    @staticmethod
    def to_run_summary(row: AgentRunTable) -> AgentRunSummary:
        return AgentRunSummary(
            run_id=row.run_id,
            project_name=row.project_name,
            origin=row.origin,
            config_name=row.config_name,
            role_name=row.role_name,
            prompt_version=row.prompt_version,
            model=row.model,
            ok=row.ok,
            error=row.error,
            latency_ms=row.latency_ms,
            agent_tokens=TokenSummary(
                input_tokens=row.agent_input_tokens,
                output_tokens=row.agent_output_tokens,
                cost_eur=row.agent_cost_eur,
            ),
            tool_tokens=TokenSummary(
                input_tokens=row.tool_input_tokens,
                output_tokens=row.tool_output_tokens,
                cost_eur=row.tool_cost_eur,
            ),
            total_tokens=TokenSummary(
                input_tokens=row.total_input_tokens,
                output_tokens=row.total_output_tokens,
                cached_tokens=row.total_cached_tokens,
                thinking_tokens=row.total_thinking_tokens,
                cost_eur=row.total_cost_eur,
            ),
            tool_names=row.tool_names.split(",") if row.tool_names else [],
            created_at=as_utc(row.created_at),
        )

    @staticmethod
    def to_tool_call_summary(row: ToolCallTable) -> ToolCallSummary:
        return ToolCallSummary(
            run_id=row.run_id,
            tool_name=row.tool_name,
            ok=row.ok,
            error=row.error,
            latency_ms=row.latency_ms,
            tokens=TokenSummary(
                input_tokens=row.input_tokens,
                output_tokens=row.output_tokens,
                cost_eur=row.cost_eur,
            ),
            created_at=as_utc(row.created_at),
        )


class Factory:
    """Write seam: domain models -> DB rows."""

    @staticmethod
    def to_run_row(record: AgentRunRecord) -> AgentRunTable:
        telemetry = record.telemetry
        total = telemetry.total_tokens
        return AgentRunTable(
            run_id=record.run_id,
            project_name=record.project_name,
            origin=record.origin.value,
            config_name=record.config_name,
            role_name=record.role_name,
            prompt_id=record.prompt_id,
            prompt_version=record.prompt_version,
            model=record.model,
            ok=record.ok,
            error=record.error,
            latency_ms=record.latency_ms,
            agent_input_tokens=telemetry.agent_tokens.input_tokens,
            agent_output_tokens=telemetry.agent_tokens.output_tokens,
            agent_cost_eur=telemetry.agent_tokens.cost_eur,
            tool_input_tokens=telemetry.tool_tokens.input_tokens,
            tool_output_tokens=telemetry.tool_tokens.output_tokens,
            tool_cost_eur=telemetry.tool_tokens.cost_eur,
            total_input_tokens=total.input_tokens,
            total_output_tokens=total.output_tokens,
            total_cached_tokens=total.cached_tokens,
            total_thinking_tokens=total.thinking_tokens,
            total_cost_eur=total.cost_eur,
            tool_names=",".join(call.name for call in telemetry.tool_calls),
            created_at=record.created_at,
        )

    @staticmethod
    def to_tool_rows(record: AgentRunRecord) -> list[ToolCallTable]:
        return [
            ToolCallTable(
                run_id=record.run_id,
                position=position,
                tool_name=call.name,
                ok=call.ok,
                error=call.error,
                latency_ms=call.latency_ms,
                input_tokens=call.tokens.input_tokens,
                output_tokens=call.tokens.output_tokens,
                cost_eur=call.tokens.cost_eur,
                created_at=record.created_at,
            )
            for position, call in enumerate(record.telemetry.tool_calls)
        ]
