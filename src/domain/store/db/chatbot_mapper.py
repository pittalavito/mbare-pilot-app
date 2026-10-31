"""Chatbots: domain chatbots, conversations, messages and automation cache
entries <-> ``chatbot`` / ``conversation`` / ``message`` / ``automation_cache`` rows."""
from domain.store.db.mapper import as_utc
from models.domain.chatbot import AutomationCacheEntry, Chatbot, ChatMessage, Conversation, MessageRole
from models.store.db import AutomationCacheTable, ChatbotTable, ConversationTable, MessageTable


class Adapter:
    """Read seam: DB rows -> domain models."""

    @staticmethod
    def to_chatbot(row: ChatbotTable) -> Chatbot:
        chatbot = Chatbot.model_validate(row.model_dump())
        chatbot.created_at = as_utc(chatbot.created_at)
        chatbot.updated_at = as_utc(chatbot.updated_at)
        return chatbot

    @staticmethod
    def to_conversation(row: ConversationTable) -> Conversation:
        conversation = Conversation.model_validate(row.model_dump())
        conversation.created_at = as_utc(conversation.created_at)
        conversation.updated_at = as_utc(conversation.updated_at)
        return conversation

    @staticmethod
    def to_message(row: MessageTable) -> ChatMessage:
        return ChatMessage(
            id=row.id,
            conversation_id=row.conversation_id,
            role=MessageRole(row.role),
            content=row.content,
            run_id=row.run_id,
            created_at=as_utc(row.created_at),
        )

    @staticmethod
    def to_automation_cache_entry(row: AutomationCacheTable) -> AutomationCacheEntry:
        entry = AutomationCacheEntry.model_validate(row.model_dump())
        entry.created_at = as_utc(entry.created_at)
        return entry


class Factory:
    """Write seam: domain models -> DB rows."""

    @staticmethod
    def to_chatbot_row(chatbot: Chatbot) -> ChatbotTable:
        return ChatbotTable(**{**chatbot.model_dump(), "tool_names": list(chatbot.tool_names)})

    @staticmethod
    def to_conversation_row(conversation: Conversation) -> ConversationTable:
        return ConversationTable(**conversation.model_dump())

    @staticmethod
    def to_message_row(message: ChatMessage) -> MessageTable:
        return MessageTable(**{**message.model_dump(), "role": message.role.value})

    @staticmethod
    def to_automation_cache_row(entry: AutomationCacheEntry) -> AutomationCacheTable:
        return AutomationCacheTable(**{**entry.model_dump(), "embedding": list(entry.embedding)})
