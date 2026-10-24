"""Chatbot domain models: a project's chatbots, their conversations and messages.
A chatbot has its own agent (system prompt, model, tools), configured in the
chatbot itself and separate from the agent configurations of the Library."""
from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from models.domain.agent import Name
from models.domain.chat import ModelKey


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Chatbot(BaseModel):
    id: int | None = None
    project_name: str
    name: Name
    description: str = ""
    system_prompt: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    prompt_version: int = Field(default=1, ge=1)
    """Incremented whenever the system prompt changes."""
    model: ModelKey
    max_steps: int = Field(default=4, ge=1, le=50)
    tool_names: list[str] = Field(default_factory=list)
    rag_enabled: bool = False
    """NOTE: placeholder, how a chatbot uses the project data is still to be defined."""
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class Conversation(BaseModel):
    id: int | None = None
    chatbot_id: int
    title: str = ""
    """From the first message; empty until then."""
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    ERROR = "error"
    """The agent could not answer: shown in the chat, never sent back to the agent."""


class ChatRoute(BaseModel):
    """A chatbot's cache entry, made by the user from one of their messages: a
    message similar enough to ``text`` launches the automation directly, with
    its fixed input, without running the chatbot's agent."""
    id: int | None = None
    chatbot_id: int
    message_id: int | None = None
    """The user message it was made from (None once that message is deleted)."""
    text: str
    embedder: str
    """Name of the embedder that made ``embedding`` (only the same one is compared)."""
    embedding: list[float]
    pipeline_id: int
    pipeline_input: str = ""
    hits: int = 0
    """Messages answered from this entry."""
    created_at: datetime = Field(default_factory=_utc_now)


class ChatRouteMatch(BaseModel):
    route: ChatRoute
    similarity: float
    """Cosine of the message and the entry's text, 0..1."""


class ChatMessage(BaseModel):
    id: int | None = None
    conversation_id: int
    role: MessageRole
    content: str
    run_id: str | None = None
    """The agent run that produced an assistant (or error) message."""
    created_at: datetime = Field(default_factory=_utc_now)
