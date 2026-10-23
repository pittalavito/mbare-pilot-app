"""Chatbots, conversations and messages (tables chatbot, conversation, message)."""
from sqlalchemy.engine import Engine
from sqlmodel import select

from domain.store.db.repository import SqlRepository
from models.store.db import ChatbotTable, ConversationTable, MessageTable


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
            .order_by(ConversationTable.updated_at.desc(), ConversationTable.id.desc())
        )
        with self._session() as session:
            return list(session.exec(statement).all())


class DbMessageRepository(SqlRepository[MessageTable]):

    def __init__(self, engine: Engine):
        super().__init__(engine, MessageTable)

    def list_for_conversation(self, conversation_id: int) -> list[MessageTable]:
        """A conversation's messages, oldest first."""
        statement = select(MessageTable).where(MessageTable.conversation_id == conversation_id).order_by(MessageTable.id)
        with self._session() as session:
            return list(session.exec(statement).all())
