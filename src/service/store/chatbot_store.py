"""The project chatbots, their conversations and messages, and the automation
cache (a chatbot's messages already answered by an automation, with their
embedding). Deleting a chatbot or a conversation takes its children with it."""
from sqlalchemy.engine import Engine

from domain.store.db.chatbot_mapper import Adapter, Factory
from domain.store.db.chatbot_repository import (
    DbAutomationCacheRepository,
    DbChatbotRepository,
    DbConversationRepository,
    DbMessageRepository,
)
from models.domain.chatbot import AutomationCacheEntry, Chatbot, ChatMessage, Conversation


class ChatbotStore:

    def __init__(self, engine: Engine):
        self._chatbots = DbChatbotRepository(engine)
        self._conversations = DbConversationRepository(engine)
        self._messages = DbMessageRepository(engine)
        self._cache_entries = DbAutomationCacheRepository(engine)

    def list_chatbots(self, project_name: str) -> list[Chatbot]:
        return [Adapter.to_chatbot(row) for row in self._chatbots.list_for_project(project_name)]

    def get_chatbot(self, chatbot_id: int) -> Chatbot | None:
        row = self._chatbots.get(chatbot_id)
        return Adapter.to_chatbot(row) if row else None

    def save_chatbot(self, chatbot: Chatbot) -> Chatbot:
        return Adapter.to_chatbot(self._chatbots.save(Factory.to_chatbot_row(chatbot)))

    def delete_chatbot(self, chatbot_id: int) -> bool:
        """Its conversations and messages go with it (DB cascade)."""
        return self._chatbots.delete(chatbot_id)

    def list_conversations(self, chatbot_id: int) -> list[Conversation]:
        """Most recently updated first."""
        return [Adapter.to_conversation(row) for row in self._conversations.list_for_chatbot(chatbot_id)]

    def get_conversation(self, conversation_id: int) -> Conversation | None:
        row = self._conversations.get(conversation_id)
        return Adapter.to_conversation(row) if row else None

    def save_conversation(self, conversation: Conversation) -> Conversation:
        return Adapter.to_conversation(self._conversations.save(Factory.to_conversation_row(conversation)))

    def delete_conversation(self, conversation_id: int) -> bool:
        """Its messages go with it (DB cascade)."""
        return self._conversations.delete(conversation_id)

    def list_messages(self, conversation_id: int) -> list[ChatMessage]:
        """Oldest first."""
        return [Adapter.to_message(row) for row in self._messages.list_for_conversation(conversation_id)]

    def get_message(self, message_id: int) -> ChatMessage | None:
        row = self._messages.get(message_id)
        return Adapter.to_message(row) if row else None

    def save_message(self, message: ChatMessage) -> ChatMessage:
        return Adapter.to_message(self._messages.save(Factory.to_message_row(message)))

    def list_automation_cache_entries(self, chatbot_id: int) -> list[AutomationCacheEntry]:
        """A chatbot's cache entries, oldest first."""
        return [Adapter.to_automation_cache_entry(row) for row in self._cache_entries.list_for_chatbot(chatbot_id)]

    def get_automation_cache_entry(self, entry_id: int) -> AutomationCacheEntry | None:
        row = self._cache_entries.get(entry_id)
        return Adapter.to_automation_cache_entry(row) if row else None

    def save_automation_cache_entry(self, entry: AutomationCacheEntry) -> AutomationCacheEntry:
        return Adapter.to_automation_cache_entry(self._cache_entries.save(Factory.to_automation_cache_row(entry)))

    def delete_automation_cache_entry(self, entry_id: int) -> bool:
        return self._cache_entries.delete(entry_id)
