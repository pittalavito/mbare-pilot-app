"""Chat endpoints: a project's chatbots (/projects/{project}/chatbots,
/chatbots/{id}), their conversations and messages, and the automation cache
of an automation chatbot (entries made from a user message:
/messages/{id}/automation-cache, /chatbots/{id}/automation-cache).
Sending a message waits for the agent's answer (no streaming yet)."""
from fastapi import APIRouter, Depends, Response, status

from controller.dependencies import automation_cache_service, chatbot_service, definition_service
from core.error import AppError, NotFoundError
from models.controller.chatbot import (
    AutomationCacheEntryRequest,
    AutomationCacheEntryResponse,
    ChatbotModelRequest,
    ChatbotRequest,
    ChatbotResponse,
    ConversationRequest,
    ConversationResponse,
    MessageRequest,
    MessageResponse,
)
from service.automation_cache_service import AutomationCacheService
from service.chatbot_service import ChatbotService
from service.definition_service import DefinitionService

router = APIRouter(tags=["chat"])


@router.get("/projects/{project}/chatbots")
def list_chatbots(project: str, service: ChatbotService = Depends(chatbot_service),
                  definitions: DefinitionService = Depends(definition_service)) -> list[ChatbotResponse]:
    return [ChatbotResponse.from_chatbot(chatbot, _origin(definitions, chatbot)) for chatbot in service.list_chatbots(project)]


def _origin(definitions: DefinitionService, chatbot) -> str | None:
    try:
        return definitions.chatbot_origin(chatbot.project_name, chatbot.name)
    except AppError:
        return None


def _saved(definitions: DefinitionService, chatbot) -> ChatbotResponse:
    """A chatbot of the files changed from the UI is written back to the data folder (plan 28): it stays after a restart."""
    try:
        definitions.save_chatbot(chatbot.project_name, chatbot)
    except AppError:
        pass
    return ChatbotResponse.from_chatbot(chatbot, _origin(definitions, chatbot))


@router.post("/projects/{project}/chatbots", status_code=status.HTTP_201_CREATED)
def create_chatbot(project: str, request: ChatbotRequest, service: ChatbotService = Depends(chatbot_service)) -> ChatbotResponse:
    body = request.model_dump()
    chatbot = service.create_chatbot(project, body.pop("name"), body.pop("system_prompt"), body.pop("model"), **body)
    return ChatbotResponse.from_chatbot(chatbot)


@router.put("/chatbots/{chatbot_id}")
def update_chatbot(chatbot_id: int, request: ChatbotRequest, service: ChatbotService = Depends(chatbot_service),
                   definitions: DefinitionService = Depends(definition_service)) -> ChatbotResponse:
    """A changed system prompt gets the next ``prompt_version``; a chatbot of the files is written back to the data folder."""
    return _saved(definitions, service.update_chatbot(chatbot_id, **request.model_dump()))


@router.post("/chatbots/{chatbot_id}/revert")
def revert_chatbot(chatbot_id: int, service: ChatbotService = Depends(chatbot_service),
                   definitions: DefinitionService = Depends(definition_service)) -> ChatbotResponse:
    """«↩ Torna al default» (plan 28): out of the data folder, the app's version applied again (404 without one)."""
    chatbot = service.get_chatbot(chatbot_id)
    definitions.revert_chatbot(chatbot.project_name, chatbot.name)
    current = service.get_chatbot(chatbot_id)
    return ChatbotResponse.from_chatbot(current, _origin(definitions, current))


@router.patch("/chatbots/{chatbot_id}/model")
def set_chatbot_model(chatbot_id: int, request: ChatbotModelRequest, service: ChatbotService = Depends(chatbot_service),
                      definitions: DefinitionService = Depends(definition_service)) -> ChatbotResponse:
    """Only the model (the UI changes nothing else); 400 when it is not usable. A chatbot of the files is written back."""
    return _saved(definitions, service.set_model(chatbot_id, request.model))


@router.delete("/chatbots/{chatbot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chatbot(chatbot_id: int, service: ChatbotService = Depends(chatbot_service)) -> Response:
    """With all its conversations; the agent runs stay in Observability."""
    if not service.delete_chatbot(chatbot_id):
        raise NotFoundError(f"Chatbot non trovato: {chatbot_id}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/chatbots/{chatbot_id}/conversations")
def list_conversations(chatbot_id: int, context: str | None = None, service: ChatbotService = Depends(chatbot_service)) -> list[ConversationResponse]:
    """Most recently updated first; ``?context=`` only those of a note (the agent panel)."""
    return [ConversationResponse.from_conversation(item) for item in service.list_conversations(chatbot_id, context)]


@router.post("/chatbots/{chatbot_id}/conversations", status_code=status.HTTP_201_CREATED)
def new_conversation(chatbot_id: int, request: ConversationRequest | None = None,
                     service: ChatbotService = Depends(chatbot_service)) -> ConversationResponse:
    """``{context}``: the note it belongs to (optional body)."""
    return ConversationResponse.from_conversation(service.new_conversation(chatbot_id, request.context if request else ""))


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: int, service: ChatbotService = Depends(chatbot_service)) -> Response:
    if not service.delete_conversation(conversation_id):
        raise NotFoundError(f"Conversazione non trovata: {conversation_id}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/conversations/{conversation_id}/messages")
def list_messages(conversation_id: int, service: ChatbotService = Depends(chatbot_service)) -> list[MessageResponse]:
    """Oldest first."""
    return [MessageResponse.from_message(message) for message in service.messages(conversation_id)]


@router.post("/conversations/{conversation_id}/messages")
def send_message(conversation_id: int, request: MessageRequest, service: ChatbotService = Depends(chatbot_service)) -> MessageResponse:
    """Saves the user's message and returns the chatbot's reply (``error`` role
    when the agent could not answer)."""
    return MessageResponse.from_message(service.send(conversation_id, request.text, request.open_note))


@router.get("/chatbots/{chatbot_id}/automation-cache")
def list_automation_cache(chatbot_id: int, service: AutomationCacheService = Depends(automation_cache_service)) -> list[AutomationCacheEntryResponse]:
    """The chatbot's cache entries, oldest first."""
    return [AutomationCacheEntryResponse.from_entry(entry) for entry in service.entries(chatbot_id)]


@router.post("/messages/{message_id}/automation-cache", status_code=status.HTTP_201_CREATED)
def add_to_automation_cache(message_id: int, request: AutomationCacheEntryRequest,
                            service: AutomationCacheService = Depends(automation_cache_service)) -> AutomationCacheEntryResponse:
    """Put a user message in its chatbot's cache: similar messages will launch
    the automation directly, without the agent."""
    return AutomationCacheEntryResponse.from_entry(service.add(message_id, request.pipeline_id, request.input))


@router.delete("/automation-cache/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_from_automation_cache(entry_id: int, service: AutomationCacheService = Depends(automation_cache_service)) -> Response:
    if not service.remove(entry_id):
        raise NotFoundError(f"Voce di cache non trovata: {entry_id}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
