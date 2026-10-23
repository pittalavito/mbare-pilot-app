"""A project's chatbots. Each has its own agent, configured in the chatbot
(system prompt, model, max steps, tools) and separate from the agent
configurations of the Library; it keeps its conversations and their messages.
Sending a message runs that agent with the conversation so far as memory, on
the chatbot's project (so project tools such as git work on it)."""
from datetime import datetime, timezone

from core.error import AppError, ConflictError, NotFoundError, ValidationError
from core.observability import LogPrefix, observed
from models.domain.agent import AgentDefinition, RunOrigin, ToolInfo
from models.domain.chatbot import ChatMessage, Chatbot, Conversation, MessageRole
from service.agent_config_service import AgentConfigService
from service.agent_service import AgentService
from service.model_service import require_usable_model
from service.store_service import StoreService

_TITLE_LENGTH = 60
_ROLE_NAME = "chatbot"
"""Recorded as the role of every chatbot run (the chatbot has no AgentRole)."""


class ChatbotService:

    def __init__(self, store_service: StoreService, agent_config_service: AgentConfigService, agent_service: AgentService):
        self._store = store_service
        self._agent_configs = agent_config_service
        self._agents = agent_service

    # -------------------------------------------------------------- chatbots
    def list_chatbots(self, project_name: str) -> list[Chatbot]:
        return self._store.list_chatbots(project_name)

    def get_chatbot(self, chatbot_id: int) -> Chatbot:
        chatbot = self._store.get_chatbot(chatbot_id)
        if chatbot is None:
            raise NotFoundError(f"Chatbot non trovato: {chatbot_id}")
        return chatbot

    def available_tools(self) -> list[ToolInfo]:
        """The tools a chatbot's agent can use."""
        return [tool for tool in self._agent_configs.list_tools() if tool.available]

    @observed(LogPrefix.CHATBOT_SERVICE)
    def create_chatbot(
        self,
        project_name: str,
        name: str,
        system_prompt: str,
        model: str,
        *,
        description: str = "",
        max_steps: int = 4,
        tool_names: list[str] | None = None,
    ) -> Chatbot:
        if self._store.get_project(project_name) is None:
            raise NotFoundError(f"Progetto non trovato: {project_name}")
        chatbot = Chatbot(
            project_name=project_name, name=name, description=description.strip(), system_prompt=system_prompt,
            model=model, max_steps=max_steps, tool_names=tool_names or [],
        )
        self._validate(chatbot)
        return self._store.save_chatbot(chatbot)

    @observed(LogPrefix.CHATBOT_SERVICE)
    def update_chatbot(
        self,
        chatbot_id: int,
        *,
        name: str,
        system_prompt: str,
        model: str,
        description: str = "",
        max_steps: int = 4,
        tool_names: list[str] | None = None,
    ) -> Chatbot:
        """Everything but the project. A changed system prompt gets the next
        ``prompt_version``, so runs say which prompt answered."""
        current = self.get_chatbot(chatbot_id)
        chatbot = Chatbot.model_validate({
            **current.model_dump(),
            "name": name, "description": description.strip(), "system_prompt": system_prompt,
            "model": model, "max_steps": max_steps, "tool_names": tool_names or [],
            "updated_at": datetime.now(timezone.utc),
        })
        if chatbot.system_prompt != current.system_prompt:
            chatbot.prompt_version = current.prompt_version + 1
        self._validate(chatbot)
        return self._store.save_chatbot(chatbot)

    def delete_chatbot(self, chatbot_id: int) -> bool:
        """With all its conversations. The agent runs stay in the history."""
        return self._store.delete_chatbot(chatbot_id)

    # --------------------------------------------------------- conversations
    def list_conversations(self, chatbot_id: int) -> list[Conversation]:
        """Most recently updated first."""
        return self._store.list_conversations(chatbot_id)

    def new_conversation(self, chatbot_id: int) -> Conversation:
        return self._store.save_conversation(Conversation(chatbot_id=self.get_chatbot(chatbot_id).id))

    def delete_conversation(self, conversation_id: int) -> bool:
        return self._store.delete_conversation(conversation_id)

    def messages(self, conversation_id: int) -> list[ChatMessage]:
        """Oldest first."""
        return self._store.list_messages(conversation_id)

    @observed(LogPrefix.CHATBOT_SERVICE)
    def send(self, conversation_id: int, text: str) -> ChatMessage:
        """Save the user's message, run the chatbot's agent with the
        conversation so far and save its answer. When the agent cannot answer
        the reply is an ERROR message (kept in the chat, never sent back to the agent)."""
        text = text.strip()
        if not text:
            raise ValidationError("Il messaggio è vuoto.")
        conversation = self._require_conversation(conversation_id)
        chatbot = self.get_chatbot(conversation.chatbot_id)
        history = self._store.list_messages(conversation_id)
        self._store.save_message(ChatMessage(conversation_id=conversation_id, role=MessageRole.USER, content=text))

        try:
            record = self._agents.run_definition(
                _agent_definition(chatbot), text, origin=RunOrigin.CHAT, history=history,
            )
        except AppError as exc:
            reply = ChatMessage(conversation_id=conversation_id, role=MessageRole.ERROR, content=str(exc))
        else:
            reply = ChatMessage(
                conversation_id=conversation_id,
                role=MessageRole.ASSISTANT if record.ok else MessageRole.ERROR,
                content=record.output if record.ok else f"L'agente non è riuscito a rispondere: {record.error}",
                run_id=record.run_id,
            )
        reply = self._store.save_message(reply)

        update = {"updated_at": datetime.now(timezone.utc)}
        if not conversation.title:
            update["title"] = text if len(text) <= _TITLE_LENGTH else text[:_TITLE_LENGTH - 1].rstrip() + "…"
        self._store.save_conversation(conversation.model_copy(update=update))
        return reply

    # ------------------------------------------------------------- helpers
    def _require_conversation(self, conversation_id: int) -> Conversation:
        conversation = self._store.get_conversation(conversation_id)
        if conversation is None:
            raise NotFoundError(f"Conversazione non trovata: {conversation_id}")
        return conversation

    def _validate(self, chatbot: Chatbot) -> None:
        """The model is usable, the tools are available, the name is unique within the project."""
        require_usable_model(self._store, chatbot.model)
        available = {tool.name for tool in self.available_tools()}
        unavailable = [name for name in chatbot.tool_names if name not in available]
        if unavailable:
            raise ValidationError(f"Tool non disponibili: {', '.join(unavailable)}")
        for other in self._store.list_chatbots(chatbot.project_name):
            if other.name.lower() == chatbot.name.lower() and other.id != chatbot.id:
                raise ConflictError(f"Esiste già un chatbot chiamato {other.name} in questo progetto.")


def _agent_definition(chatbot: Chatbot) -> AgentDefinition:
    """The chatbot's own agent, as AgentService runs and records it."""
    return AgentDefinition(
        name=f"chatbot/{chatbot.name}",
        role_name=_ROLE_NAME,
        prompt_id=0,
        prompt_version=chatbot.prompt_version,
        system_prompt=chatbot.system_prompt,
        model=chatbot.model,
        max_steps=chatbot.max_steps,
        tool_names=chatbot.tool_names,
        project_name=chatbot.project_name,
    )
