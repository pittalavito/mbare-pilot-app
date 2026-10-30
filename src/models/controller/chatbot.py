"""Request/response models of the chat API: a project's chatbots, their
conversations and messages."""
from datetime import datetime

from pydantic import BaseModel, Field

from models.domain.chatbot import AutomationCacheEntry, Chatbot, ChatbotKind, ChatMessage, Conversation


class ChatbotResponse(BaseModel):
    id: int
    project_name: str
    name: str
    kind: ChatbotKind
    """``automation``: fixed tools (``tool_names``) and the automation cache; ``custom``: tools chosen freely."""
    description: str
    system_prompt: str
    prompt_version: int
    model: str
    max_steps: int
    tool_names: list[str]

    @classmethod
    def from_chatbot(cls, chatbot: Chatbot) -> "ChatbotResponse":
        return cls(**chatbot.model_dump())


class ChatbotRequest(BaseModel):
    """Create and update: the project comes from the URL and never changes."""
    name: str
    kind: ChatbotKind = ChatbotKind.CUSTOM
    """``automation``: ``tool_names`` is ignored, its tools are the fixed ones."""
    description: str = ""
    system_prompt: str
    model: str
    max_steps: int = 4
    tool_names: list[str] = Field(default_factory=list)


class ConversationResponse(BaseModel):
    id: int
    chatbot_id: int
    title: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_conversation(cls, conversation: Conversation) -> "ConversationResponse":
        return cls(**conversation.model_dump())


class MessageResponse(BaseModel):
    id: int
    conversation_id: int
    role: str
    """``user`` | ``assistant`` | ``error`` (the agent could not answer)."""
    content: str
    run_id: str | None
    created_at: datetime

    @classmethod
    def from_message(cls, message: ChatMessage) -> "MessageResponse":
        return cls(**message.model_dump())


class MessageRequest(BaseModel):
    text: str


class AutomationCacheEntryResponse(BaseModel):
    """A cache entry of a chatbot (without its embedding)."""
    id: int
    chatbot_id: int
    message_id: int | None
    """The user message it was made from (None once deleted)."""
    text: str
    pipeline_id: int
    pipeline_input: str
    hits: int
    created_at: datetime

    @classmethod
    def from_entry(cls, entry: AutomationCacheEntry) -> "AutomationCacheEntryResponse":
        return cls(**entry.model_dump(exclude={"embedder", "embedding"}))


class AutomationCacheEntryRequest(BaseModel):
    """Put a user message in cache: similar messages launch this automation, with this fixed input."""
    pipeline_id: int
    input: str = ""
