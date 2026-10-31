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
    DbAutomationCacheRepository,
    DbChatbotRepository,
    DbConversationRepository,
    DbMessageRepository,
)
from domain.store.db.copilot_repository import USAGE_COLUMNS, DbCopilotMessageRepository, DbCopilotSessionRepository, DbCopilotTurnRepository
from domain.store.db.pipeline_repository import (
    DbPipelineEdgeRepository,
    DbPipelineRepository,
    DbPipelineRunRepository,
    DbPipelineStepRepository,
    DbPipelineStepRunRepository,
)
from domain.store.db.project_repository import DbProjectRepository
from domain.store.db.prompt_repository import DbPromptRepository
from domain.store.db.repository import Engine, transaction
from domain.store.db.role_repository import DbRoleRepository
from models.domain.agent import (
    AgentConfig,
    AgentRole,
    SystemPrompt,
)
from models.domain.atlassian import AtlassianFavorite, AtlassianSettings, FavoriteKind
from models.domain.chat import EmbeddingModelName
from models.domain.chatbot import AutomationCacheEntry, Chatbot, ChatMessage, Conversation, MessageRole
from models.domain.copilot import (
    CopilotMessage,
    CopilotMessageRole,
    CopilotModelUsage,
    CopilotPhase,
    CopilotSession,
    CopilotSessionStatus,
    CopilotTurnRecord,
    CopilotUsage,
)
from models.domain.note import NoteType
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
    AtlassianFavoriteTable,
    AutomationCacheTable,
    ChatbotTable,
    ConversationTable,
    CopilotMessageTable,
    CopilotSessionTable,
    CopilotTurnTable,
    MessageTable,
    PipelineEdgeTable,
    PipelineRunTable,
    PipelineStepRunTable,
    PipelineStepTable,
    PipelineTable,
    ProjectAtlassianTable,
    ProjectTable,
    SystemPromptTable,
)

__all__ = [
    "Engine",
    "transaction",
    "DbAgentConfigRepository",
    "DbAtlassianFavoriteRepository",
    "DbAtlassianRepository",
    "DbChatbotRepository",
    "DbAutomationCacheRepository",
    "DbConversationRepository",
    "DbMessageRepository",
    "DbPipelineEdgeRepository",
    "DbPipelineRepository",
    "DbPipelineRunRepository",
    "DbPipelineStepRepository",
    "DbPipelineStepRunRepository",
    "DbCopilotMessageRepository",
    "DbCopilotSessionRepository",
    "DbCopilotTurnRepository",
    "DbProjectRepository",
    "DbPromptRepository",
    "DbRoleRepository",
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
    def to_copilot_turn(row: CopilotTurnTable) -> CopilotTurnRecord:
        data = row.model_dump()
        usage = CopilotUsage(**{name: data.pop(name) for name in USAGE_COLUMNS})
        return CopilotTurnRecord(**{**data, "phase": CopilotPhase(row.phase), "usage": usage, "created_at": _as_utc(row.created_at)})

    @staticmethod
    def to_copilot_model_usage(row: tuple) -> CopilotModelUsage:
        """A row of ``totals_by_model``: ``(model, turns, *usage sums)``."""
        return CopilotModelUsage(model=row[0], turns=row[1], usage=CopilotUsage(**dict(zip(USAGE_COLUMNS, row[2:], strict=False))))

    @staticmethod
    def to_copilot_message(row: CopilotMessageTable) -> CopilotMessage:
        return CopilotMessage(**{**row.model_dump(), "role": CopilotMessageRole(row.role), "created_at": _as_utc(row.created_at)})



    @staticmethod
    def to_role(row: AgentRoleTable) -> AgentRole:
        return AgentRole.model_validate(row.model_dump())

    @staticmethod
    def to_prompt(row: SystemPromptTable) -> SystemPrompt:
        prompt = SystemPrompt.model_validate(row.model_dump())
        prompt.created_at = _as_utc(prompt.created_at)
        return prompt

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
            visible_note_types=[NoteType(value) for value in row.visible_note_types if value in NoteType.__members__.values()]
            if row.visible_note_types is not None else None,
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
    def to_automation_cache_entry(row: AutomationCacheTable) -> AutomationCacheEntry:
        entry = AutomationCacheEntry.model_validate(row.model_dump())
        entry.created_at = _as_utc(entry.created_at)
        return entry

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
                model=row.model or "",
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
    def to_copilot_turn_row(turn: CopilotTurnRecord) -> CopilotTurnTable:
        data = turn.model_dump(exclude={"usage"})
        return CopilotTurnTable(**{**data, **turn.usage.model_dump(), "phase": turn.phase.value})

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
    def to_automation_cache_row(entry: AutomationCacheEntry) -> AutomationCacheTable:
        return AutomationCacheTable(**{**entry.model_dump(), "embedding": list(entry.embedding)})

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
            visible_note_types=[kind.value for kind in project.visible_note_types] if project.visible_note_types is not None else None,
            created_at=project.created_at,
        )

    @staticmethod
    def to_role_row(role: AgentRole) -> AgentRoleTable:
        return AgentRoleTable(**role.model_dump())

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
