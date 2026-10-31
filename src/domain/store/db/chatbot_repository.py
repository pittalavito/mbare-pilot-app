"""Chatbots, conversations, messages and the chatbots' cache (tables chatbot,
conversation, message, automation_cache)."""
from sqlalchemy.engine import Engine
from sqlmodel import col, select

from domain.store.db.repository import SqlRepository
from models.store.db import AutomationCacheTable, ChatbotTable, ConversationTable, MessageTable


class DbChatbotRepository(SqlRepository[ChatbotTable]):

    def __init__(self, engine: Engine):
        super().__init__(engine, ChatbotTable)

    def list_for_project(self, project_name: str) -> list[ChatbotTable]:
        """A project's chatbots, sorted by name."""
        statement = select(ChatbotTable).where(ChatbotTable.project_name == project_name).order_by(ChatbotTable.name)
        with self._session() as session:
            return list(session.exec(statement).all())


class DbConversationRepository(SqlRepository[ConversationTable]):

    def __init__(self, engine: Engine):
        super().__init__(engine, ConversationTable)

    def list_for_chatbot(self, chatbot_id: int) -> list[ConversationTable]:
        """A chatbot's conversations, most recently updated first."""
        statement = (
            select(ConversationTable)
            .where(ConversationTable.chatbot_id == chatbot_id)
            .order_by(col(ConversationTable.updated_at).desc(), col(ConversationTable.id).desc())
        )
        with self._session() as session:
            return list(session.exec(statement).all())


class DbMessageRepository(SqlRepository[MessageTable]):

    def __init__(self, engine: Engine):
        super().__init__(engine, MessageTable)

    def list_for_conversation(self, conversation_id: int) -> list[MessageTable]:
        """A conversation's messages, oldest first."""
        statement = select(MessageTable).where(col(MessageTable.conversation_id) == conversation_id).order_by(col(MessageTable.id))
        with self._session() as session:
            return list(session.exec(statement).all())


class DbAutomationCacheRepository(SqlRepository[AutomationCacheTable]):

    def __init__(self, engine: Engine):
        super().__init__(engine, AutomationCacheTable)

    def list_for_chatbot(self, chatbot_id: int) -> list[AutomationCacheTable]:
        """A chatbot's cache entries, oldest first."""
        statement = select(AutomationCacheTable).where(col(AutomationCacheTable.chatbot_id) == chatbot_id).order_by(col(AutomationCacheTable.id))
        with self._session() as session:
            return list(session.exec(statement).all())
