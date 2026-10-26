"""DB store facade: one import point for the DB persistence layer.

Re-exports the DB repositories and holds the two translation seams as
static-method classes: ``Adapter`` (rows -> domain models, reads) and
``Factory`` (domain models -> rows, writes).
"""
from datetime import datetime, timezone

from domain.store.db.agent_config_repository import DbAgentConfigRepository
from domain.store.db.atlassian_favorite_repository import DbAtlassianFavoriteRepository
from domain.store.db.atlassian_repository import DbAtlassianRepository
from domain.store.db.chatbot_repository import (
    DbChatbotRepository,
    DbChatRouteRepository,
    DbConversationRepository,
    DbMessageRepository,
)
from domain.store.db.pipeline_repository import (
    DbPipelineEdgeRepository,
    DbPipelineRepository,
    DbPipelineRunRepository,
    DbPipelineStepRepository,
    DbPipelineStepRunRepository,
)
from domain.store.db.chat_model_repository import DbChatModelRepository
from domain.store.db.copilot_repository import DbCopilotMessageRepository, DbCopilotSessionRepository
from domain.store.db.project_repository import DbProjectRepository
from domain.store.db.prompt_repository import DbPromptRepository
from domain.store.db.repository import Engine
from domain.store.db.role_repository import DbRoleRepository
from domain.store.db.run_repository import DbRunRepository
from domain.store.db.tool_repository import DbToolRepository
from models.domain.agent import (
    AgentConfig,
    AgentRole,
    AgentRunRecord,
    AgentRunSummary,
    SystemPrompt,
    TokenSummary,
    ToolCallSummary,
    ToolInfo,
)
from models.domain.atlassian import AtlassianFavorite, AtlassianSettings, FavoriteKind
from models.domain.chat import ChatModel, EmbeddingModelName
from models.domain.chatbot import ChatMessage, ChatRoute, Chatbot, Conversation, MessageRole
from models.domain.copilot import CopilotMessage, CopilotMessageRole, CopilotSession, CopilotSessionStatus
from models.domain.pipeline import (
    INPUT_NODE,
    EdgeConditionKind,
    Pipeline,
    PipelineEdge,
    PipelineRun,
    PipelineStep,
    PipelineStepRun,
    RunStatus,
    StepAgent,
    StepKind,
)
from models.domain.project import Project, ProjectSource
from models.store.db import (
    AgentConfigTable,
    AgentRoleTable,
    AgentRunTable,
    AtlassianFavoriteTable,
    ChatbotTable,
    ChatRouteTable,
    ConversationTable,
    CopilotMessageTable,
    CopilotSessionTable,
    MessageTable,
    ChatModelTable,
    PipelineEdgeTable,
    PipelineRunTable,
    PipelineStepRunTable,
    PipelineStepTable,
    PipelineTable,
    ProjectAtlassianTable,
    ProjectTable,
    SystemPromptTable,
    ToolCallTable,
    ToolTable,
)

__all__ = [
    "Engine",
    "DbAgentConfigRepository",
    "DbAtlassianFavoriteRepository",
    "DbAtlassianRepository",
    "DbChatbotRepository",
    "DbChatRouteRepository",
    "DbConversationRepository",
    "DbMessageRepository",
    "DbPipelineEdgeRepository",
    "DbPipelineRepository",
    "DbPipelineRunRepository",
    "DbPipelineStepRepository",
    "DbPipelineStepRunRepository",
    "DbChatModelRepository",
    "DbCopilotMessageRepository",
    "DbCopilotSessionRepository",
    "DbProjectRepository",
    "DbPromptRepository",
    "DbRoleRepository",
    "DbRunRepository",
    "DbToolRepository",
    "Adapter",
    "Factory",
]


def _as_utc(value: datetime) -> datetime:
    """Backends without timezone support (e.g. SQLite) return naive datetimes: they are UTC."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class Adapter:
    """Read seam: DB rows -> domain models."""

    @staticmethod
    def to_copilot_session(row: CopilotSessionTable) -> CopilotSession:
        return CopilotSession(**{
            **row.model_dump(),
            "status": CopilotSessionStatus(row.status),
            "created_at": _as_utc(row.created_at),
            "updated_at": _as_utc(row.updated_at),
            "started_at": _as_utc(row.started_at) if row.started_at else None,
            "finished_at": _as_utc(row.finished_at) if row.finished_at else None,
        })

    @staticmethod
    def to_copilot_message(row: CopilotMessageTable) -> CopilotMessage:
        return CopilotMessage(**{**row.model_dump(), "role": CopilotMessageRole(row.role), "created_at": _as_utc(row.created_at)})

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
            created_at=_as_utc(row.created_at),
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
            created_at=_as_utc(row.created_at),
        )

    @staticmethod
    def to_chat_model(row: ChatModelTable) -> ChatModel:
        return ChatModel.model_validate(row.model_dump())

    @staticmethod
    def to_role(row: AgentRoleTable) -> AgentRole:
        return AgentRole.model_validate(row.model_dump())

    @staticmethod
    def to_prompt(row: SystemPromptTable) -> SystemPrompt:
        prompt = SystemPrompt.model_validate(row.model_dump())
        prompt.created_at = _as_utc(prompt.created_at)
        return prompt

    @staticmethod
    def to_tool(row: ToolTable, available: bool) -> ToolInfo:
        return ToolInfo(name=row.name, description=row.description, available=available)

    @staticmethod
    def to_agent_config(row: AgentConfigTable) -> AgentConfig:
        return AgentConfig(
            name=row.name,
            project_name=row.project_name,
            description=row.description,
            role_name=row.role_name,
            prompt_id=row.prompt_id,
            model=row.model,
            max_steps=row.max_steps,
            tool_names=list(row.tool_names),
        )


    @staticmethod
    def to_project(row: ProjectTable) -> Project:
        return Project(
            name=row.name,
            description=row.description,
            source=ProjectSource(row.source),
            root_path=row.root_path,
            embedding_model=EmbeddingModelName(row.embedding_model),
            created_at=_as_utc(row.created_at),
        )

    @staticmethod
    def to_chatbot(row: ChatbotTable) -> Chatbot:
        chatbot = Chatbot.model_validate(row.model_dump())
        chatbot.created_at = _as_utc(chatbot.created_at)
        chatbot.updated_at = _as_utc(chatbot.updated_at)
        return chatbot

    @staticmethod
    def to_conversation(row: ConversationTable) -> Conversation:
        conversation = Conversation.model_validate(row.model_dump())
        conversation.created_at = _as_utc(conversation.created_at)
        conversation.updated_at = _as_utc(conversation.updated_at)
        return conversation

    @staticmethod
    def to_message(row: MessageTable) -> ChatMessage:
        return ChatMessage(
            id=row.id,
            conversation_id=row.conversation_id,
            role=MessageRole(row.role),
            content=row.content,
            run_id=row.run_id,
            created_at=_as_utc(row.created_at),
        )

    @staticmethod
    def to_chat_route(row: ChatRouteTable) -> ChatRoute:
        route = ChatRoute.model_validate(row.model_dump())
        route.created_at = _as_utc(route.created_at)
        return route

    @staticmethod
    def to_pipeline(row: PipelineTable, step_rows: list[PipelineStepTable],
                    edge_rows: list[PipelineEdgeTable] | None = None) -> Pipeline:
        names = {step_row.id: step_row.name for step_row in step_rows}
        return Pipeline(
            id=row.id,
            project_name=row.project_name,
            name=row.name,
            description=row.description,
            active=row.active,
            steps=[Adapter.to_pipeline_step(step_row) for step_row in step_rows],
            edges=[
                PipelineEdge(
                    source=INPUT_NODE if edge_row.source_step_id is None else names[edge_row.source_step_id],
                    target=names[edge_row.target_step_id],
                    condition=EdgeConditionKind(edge_row.condition), value=edge_row.value,
                )
                for edge_row in edge_rows or []
                if edge_row.target_step_id in names and (edge_row.source_step_id is None or edge_row.source_step_id in names)
            ],
            created_at=_as_utc(row.created_at),
            updated_at=_as_utc(row.updated_at),
        )

    @staticmethod
    def to_pipeline_step(row: PipelineStepTable) -> PipelineStep:
        kind = StepKind(row.kind)
        agent = None
        if kind is StepKind.AGENT:
            agent = StepAgent(
                system_prompt=row.system_prompt or "",
                prompt_version=row.prompt_version,
                model=row.model,
                max_steps=row.max_steps or 4,
                tool_names=list(row.tool_names),
            )
        return PipelineStep(
            id=row.id,
            name=row.name,
            kind=kind,
            input_template=row.input_template,
            agent=agent,
            agent_config_name=row.agent_config_name,
            function_name=row.function_name,
            params=dict(row.params),
            position_x=row.position_x,
            position_y=row.position_y,
        )

    @staticmethod
    def to_pipeline_run(row: PipelineRunTable, step_rows: list[PipelineStepRunTable] | None = None) -> PipelineRun:
        return PipelineRun(
            id=row.id,
            pipeline_id=row.pipeline_id,
            status=RunStatus(row.status),
            input=row.input,
            output=row.output,
            error=row.error,
            created_at=_as_utc(row.created_at),
            started_at=_as_utc(row.started_at) if row.started_at else None,
            finished_at=_as_utc(row.finished_at) if row.finished_at else None,
            steps=[Adapter.to_pipeline_step_run(step_row) for step_row in step_rows or []],
        )

    @staticmethod
    def to_pipeline_step_run(row: PipelineStepRunTable) -> PipelineStepRun:
        step_run = PipelineStepRun.model_validate(row.model_dump())
        step_run.started_at = _as_utc(step_run.started_at) if step_run.started_at else None
        step_run.finished_at = _as_utc(step_run.finished_at) if step_run.finished_at else None
        return step_run

    @staticmethod
    def to_atlassian_settings(row: ProjectAtlassianTable, api_token: str) -> AtlassianSettings:
        """``api_token`` is the decrypted ``row.api_token``."""
        return AtlassianSettings.model_validate({**row.model_dump(), "api_token": api_token})

    @staticmethod
    def to_atlassian_favorite(row: AtlassianFavoriteTable) -> AtlassianFavorite:
        favorite = AtlassianFavorite.model_validate({**row.model_dump(), "kind": FavoriteKind(row.kind)})
        favorite.created_at = _as_utc(favorite.created_at)
        return favorite


class Factory:
    """Write seam: domain models -> DB rows."""

    @staticmethod
    def to_copilot_session_row(session: CopilotSession) -> CopilotSessionTable:
        return CopilotSessionTable(**{**session.model_dump(), "status": session.status.value, "changed_files": list(session.changed_files)})

    @staticmethod
    def to_copilot_message_row(message: CopilotMessage) -> CopilotMessageTable:
        return CopilotMessageTable(**{**message.model_dump(), "role": message.role.value})

    @staticmethod
    def to_chatbot_row(chatbot: Chatbot) -> ChatbotTable:
        return ChatbotTable(**{**chatbot.model_dump(), "tool_names": list(chatbot.tool_names)})

    @staticmethod
    def to_conversation_row(conversation: Conversation) -> ConversationTable:
        return ConversationTable(**conversation.model_dump())

    @staticmethod
    def to_pipeline_row(pipeline: Pipeline) -> PipelineTable:
        return PipelineTable(**pipeline.model_dump(exclude={"steps", "edges"}))

    @staticmethod
    def to_pipeline_step_row(step: PipelineStep, pipeline_id: int, position: int) -> PipelineStepTable:
        agent = step.agent
        return PipelineStepTable(
            id=step.id,
            pipeline_id=pipeline_id,
            position=position,
            name=step.name,
            kind=step.kind.value,
            input_template=step.input_template,
            system_prompt=agent.system_prompt if agent else None,
            prompt_version=agent.prompt_version if agent else 1,
            model=agent.model if agent else None,
            max_steps=agent.max_steps if agent else None,
            tool_names=list(agent.tool_names) if agent else [],
            agent_config_name=step.agent_config_name,
            function_name=step.function_name,
            params=dict(step.params),
            position_x=step.position_x,
            position_y=step.position_y,
        )

    @staticmethod
    def to_pipeline_edge_row(edge: PipelineEdge, pipeline_id: int, step_ids: dict[str, int]) -> PipelineEdgeTable:
        """``step_ids``: the saved steps' ids by name."""
        return PipelineEdgeTable(
            pipeline_id=pipeline_id,
            source_step_id=None if edge.source == INPUT_NODE else step_ids[edge.source],
            target_step_id=step_ids[edge.target],
            condition=edge.condition.value,
            value=edge.value,
        )

    @staticmethod
    def to_pipeline_run_row(run: PipelineRun) -> PipelineRunTable:
        return PipelineRunTable(**{**run.model_dump(exclude={"steps"}), "status": run.status.value})

    @staticmethod
    def to_pipeline_step_run_row(step_run: PipelineStepRun) -> PipelineStepRunTable:
        return PipelineStepRunTable(
            **{**step_run.model_dump(), "kind": step_run.kind.value, "status": step_run.status.value},
        )

    @staticmethod
    def to_message_row(message: ChatMessage) -> MessageTable:
        return MessageTable(**{**message.model_dump(), "role": message.role.value})

    @staticmethod
    def to_chat_route_row(route: ChatRoute) -> ChatRouteTable:
        return ChatRouteTable(**{**route.model_dump(), "embedding": list(route.embedding)})

    @staticmethod
    def to_atlassian_row(settings: AtlassianSettings, encrypted_token: str) -> ProjectAtlassianTable:
        return ProjectAtlassianTable(
            project_name=settings.project_name,
            base_url=settings.base_url,
            email=settings.email,
            api_token=encrypted_token,
            jira_project_key=settings.jira_project_key,
            confluence_space_key=settings.confluence_space_key,
        )

    @staticmethod
    def to_atlassian_favorite_row(favorite: AtlassianFavorite) -> AtlassianFavoriteTable:
        return AtlassianFavoriteTable(**{**favorite.model_dump(), "kind": favorite.kind.value})

    @staticmethod
    def to_project_row(project: Project) -> ProjectTable:
        return ProjectTable(
            name=project.name,
            description=project.description,
            source=project.source.value,
            root_path=project.root_path,
            embedding_model=project.embedding_model.value,
            created_at=project.created_at,
        )

    @staticmethod
    def to_chat_model_row(chat_model: ChatModel) -> ChatModelTable:
        return ChatModelTable(**{**chat_model.model_dump(), "provider": chat_model.provider.value})

    @staticmethod
    def to_role_row(role: AgentRole) -> AgentRoleTable:
        return AgentRoleTable(**role.model_dump())

    @staticmethod
    def to_tool_row(tool: ToolInfo) -> ToolTable:
        return ToolTable(name=tool.name, description=tool.description)

    @staticmethod
    def to_agent_config_row(config: AgentConfig) -> AgentConfigTable:
        return AgentConfigTable(
            name=config.name,
            project_name=config.project_name,
            description=config.description,
            role_name=config.role_name,
            prompt_id=config.prompt_id,
            model=config.model,
            max_steps=config.max_steps,
            tool_names=list(config.tool_names),
        )

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
