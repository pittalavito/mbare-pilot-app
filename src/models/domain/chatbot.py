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


class ChatbotKind(StrEnum):
    AUTOMATION = "automation"
    """Launches the project's automations and checks how they went: only
    KIND_TOOLS' tools (whatever is saved), and the automation cache."""
    SECRETARY = "secretary"
    """Helps with the notes: reads, creates and ticks the todo lists, reads the
    agent tasks' status; never the references. Only KIND_TOOLS' tools, no cache."""
    CUSTOM = "custom"
    """Its tools are chosen freely; no automation cache."""


KIND_TOOLS: dict[ChatbotKind, list[str]] = {
    ChatbotKind.AUTOMATION: ["list_automations", "run_automation", "automation_status"],
    ChatbotKind.SECRETARY: ["list_todo_lists", "read_todo_list", "create_todo_list", "update_todo_list", "list_agent_tasks"],
}
"""The tools a kind imposes on its chatbots; a kind not here lets them be chosen."""


class Chatbot(BaseModel):
    id: int | None = None
    project_name: str
    name: Name
    kind: ChatbotKind = ChatbotKind.CUSTOM
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

    @property
    def has_automation_cache(self) -> bool:
        return self.kind is ChatbotKind.AUTOMATION

    def with_kind_tools(self) -> "Chatbot":
        """The chatbot with the tools its kind imposes (unchanged for a free kind)."""
        tools = KIND_TOOLS.get(self.kind)
        return self if tools is None or self.tool_names == tools else self.model_copy(update={"tool_names": list(tools)})


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


class AutomationCacheEntry(BaseModel):
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


class AutomationCacheMatch(BaseModel):
    entry: AutomationCacheEntry
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
