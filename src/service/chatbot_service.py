"""A project's chatbots. Each has its own agent, configured in the chatbot
(system prompt, model, max steps, tools) and separate from the agent
configurations of the Library; it keeps its conversations and their messages.
Sending a message runs that agent with the conversation so far as memory, on
the chatbot's project (so project tools such as git work on it), unless the
message is close enough to one the user put in cache: then its automation is
launched directly, without the agent (AutomationCacheService)."""
from datetime import datetime, timezone

from core.error import AppError, ConflictError, NotFoundError, ValidationError
from core.observability import LogPrefix, observed
from models.domain.agent import AgentDefinition, RunOrigin, ToolInfo
from models.domain.chatbot import AutomationCacheEntry, Chatbot, ChatbotKind, ChatMessage, Conversation, MessageRole
from service.agent_config_service import AgentConfigService
from service.agent_service import AgentService
from service.automation_cache_service import CACHE_BYPASS, AutomationCacheService
from service.model_service import require_usable_model
from service.store.catalog_store import CatalogStore
from service.store.chatbot_store import ChatbotStore
from service.store.project_store import ProjectStore

_TITLE_LENGTH = 60
_ROLE_NAME = "chatbot"
"""Recorded as the role of every chatbot run (the chatbot has no AgentRole)."""
_CACHE_MARK = "⚡"
"""Starts the replies given from the cache (no agent run behind them)."""


class ChatbotService:

    def __init__(self, chatbots: ChatbotStore, projects: ProjectStore, catalog: CatalogStore,
                 agent_config_service: AgentConfigService, agent_service: AgentService,
                 automation_cache: AutomationCacheService | None = None):
        """``automation_cache`` is the cache; None = every message goes to the agent."""
        self._chatbots = chatbots
        self._projects = projects
        self._catalog = catalog
        self._agent_configs = agent_config_service
        self._agents = agent_service
        self._cache = automation_cache

    # -------------------------------------------------------------- chatbots
    def list_chatbots(self, project_name: str) -> list[Chatbot]:
        return self._chatbots.list_chatbots(project_name)

    def get_chatbot(self, chatbot_id: int) -> Chatbot:
        chatbot = self._chatbots.get_chatbot(chatbot_id)
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
        kind: ChatbotKind = ChatbotKind.CUSTOM,
    ) -> Chatbot:
        """``kind`` automation: its tools are the fixed ones, whatever ``tool_names`` says."""
        if self._projects.get(project_name) is None:
            raise NotFoundError(f"Progetto non trovato: {project_name}")
        chatbot = Chatbot(
            project_name=project_name,
            name=name,
            kind=kind,
            description=description.strip(),
            system_prompt=system_prompt,
            model=model,
            max_steps=max_steps,
            tool_names=tool_names or [],
        ).with_kind_tools()
        self._validate(chatbot)
        return self._chatbots.save_chatbot(chatbot)

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
        kind: ChatbotKind | None = None,
    ) -> Chatbot:
        """Everything but the project (``kind`` None = unchanged). A changed
        system prompt gets the next ``prompt_version``, so runs say which
        prompt answered."""
        current = self.get_chatbot(chatbot_id)
        chatbot = Chatbot.model_validate({
            **current.model_dump(),
            "name": name,
            "kind": kind or current.kind,
            "description": description.strip(),
            "system_prompt": system_prompt,
            "model": model,
            "max_steps": max_steps,
            "tool_names": tool_names or [],
            "updated_at": datetime.now(timezone.utc),
        }).with_kind_tools()
        if chatbot.system_prompt != current.system_prompt:
            chatbot.prompt_version = current.prompt_version + 1
        self._validate(chatbot)
        return self._chatbots.save_chatbot(chatbot)

    def set_model(self, chatbot_id: int, model: str) -> Chatbot:
        """Only the model, the rest as it is (the prompt keeps its version).
        ValidationError when the model is not usable. A sync of the
        definition files that defines this chatbot sets its model again."""
        current = self.get_chatbot(chatbot_id)
        chatbot = current.model_copy(update={"model": model.strip(), "updated_at": datetime.now(timezone.utc)})
        require_usable_model(self._catalog, chatbot.model)
        return self._chatbots.save_chatbot(chatbot)

    def delete_chatbot(self, chatbot_id: int) -> bool:
        """With all its conversations. The agent runs stay in the history."""
        return self._chatbots.delete_chatbot(chatbot_id)

    # --------------------------------------------------------- conversations
    def list_conversations(self, chatbot_id: int) -> list[Conversation]:
        """Most recently updated first."""
        return self._chatbots.list_conversations(chatbot_id)

    def new_conversation(self, chatbot_id: int) -> Conversation:
        return self._chatbots.save_conversation(Conversation(chatbot_id=self.get_chatbot(chatbot_id).id))

    def delete_conversation(self, conversation_id: int) -> bool:
        return self._chatbots.delete_conversation(conversation_id)

    def messages(self, conversation_id: int) -> list[ChatMessage]:
        """Oldest first."""
        return self._chatbots.list_messages(conversation_id)

    @observed(LogPrefix.CHATBOT_SERVICE)
    def send(self, conversation_id: int, text: str) -> ChatMessage:
        """Save the user's message and answer it: from the cache when it is
        close enough to an entry (its automation is launched, no agent), else
        by running the chatbot's agent with the conversation so far. A message
        starting with ``!`` skips the cache. When the answer fails the reply is
        an ERROR message (kept in the chat, never sent back to the agent)."""
        text = text.strip()
        bypass = text.startswith(CACHE_BYPASS)
        request = text.removeprefix(CACHE_BYPASS).strip()
        if not request:
            raise ValidationError("Il messaggio è vuoto.")
        conversation = self._require_conversation(conversation_id)
        chatbot = self.get_chatbot(conversation.chatbot_id).with_kind_tools()  # its kind's tools, even if the DB says otherwise
        history = self._chatbots.list_messages(conversation_id)
        self._chatbots.save_message(ChatMessage(conversation_id=conversation_id, role=MessageRole.USER, content=text))

        match = None if bypass or self._cache is None or not chatbot.has_automation_cache else self._cache.match(chatbot.id, request)
        if match is not None:
            reply = self._from_cache(conversation_id, match.entry)
        else:
            reply = self._from_agent(conversation_id, chatbot, request, history)
        reply = self._chatbots.save_message(reply)

        update = {"updated_at": datetime.now(timezone.utc)}
        if not conversation.title:
            update["title"] = text if len(text) <= _TITLE_LENGTH else text[:_TITLE_LENGTH - 1].rstrip() + "…"
        self._chatbots.save_conversation(conversation.model_copy(update=update))
        return reply

    # ------------------------------------------------------------- helpers
    def _from_cache(self, conversation_id: int, entry: AutomationCacheEntry) -> ChatMessage:
        try:
            pipeline, run = self._cache.launch(entry)
        except AppError as exc:
            return ChatMessage(
                conversation_id=conversation_id,
                role=MessageRole.ERROR,
                content=f"{_CACHE_MARK} Dalla cache, ma l'automation non è partita: {exc}"
            )
        return ChatMessage(
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content=f"{_CACHE_MARK} Ho lanciato l'automation {pipeline.name} (id {run.id})."
        )

    def _from_agent(self, conversation_id: int, chatbot: Chatbot, text: str, history: list[ChatMessage]) -> ChatMessage:
        try:
            record = self._agents.run_definition(_agent_definition(chatbot), text, origin=RunOrigin.CHAT, history=history,)
        except AppError as exc:
            return ChatMessage(conversation_id=conversation_id, role=MessageRole.ERROR, content=str(exc))
        return ChatMessage(
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT if record.ok else MessageRole.ERROR,
            content=record.output if record.ok else f"L'agente non è riuscito a rispondere: {record.error}",
            run_id=record.run_id,
        )

    def _require_conversation(self, conversation_id: int) -> Conversation:
        conversation = self._chatbots.get_conversation(conversation_id)
        if conversation is None:
            raise NotFoundError(f"Conversazione non trovata: {conversation_id}")
        return conversation

    def _validate(self, chatbot: Chatbot) -> None:
        """The model is usable, the tools are available, the name is unique within the project."""
        require_usable_model(self._catalog, chatbot.model)
        available = {tool.name for tool in self.available_tools()}
        unavailable = [name for name in chatbot.tool_names if name not in available]
        if unavailable:
            raise ValidationError(f"Tool non disponibili: {', '.join(unavailable)}")
        for other in self._chatbots.list_chatbots(chatbot.project_name):
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
