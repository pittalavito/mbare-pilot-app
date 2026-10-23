"""Chat endpoints: a project's chatbots (/projects/{project}/chatbots,
/chatbots/{id}), their conversations and messages. Sending a message waits
for the agent's answer (no streaming yet)."""
from fastapi import APIRouter, Depends, Response, status

from controller.dependencies import chatbot_service
from core.error import NotFoundError
from models.controller.chatbot import (
    ChatbotRequest, ChatbotResponse, ConversationResponse, MessageRequest, MessageResponse,
)
from service.chatbot_service import ChatbotService

router = APIRouter(tags=["chat"])


@router.get("/projects/{project}/chatbots")
def list_chatbots(project: str, service: ChatbotService = Depends(chatbot_service)) -> list[ChatbotResponse]:
    return [ChatbotResponse.from_chatbot(chatbot) for chatbot in service.list_chatbots(project)]


@router.post("/projects/{project}/chatbots", status_code=status.HTTP_201_CREATED)
def create_chatbot(project: str, request: ChatbotRequest,
                   service: ChatbotService = Depends(chatbot_service)) -> ChatbotResponse:
    body = request.model_dump()
    chatbot = service.create_chatbot(project, body.pop("name"), body.pop("system_prompt"), body.pop("model"), **body)
    return ChatbotResponse.from_chatbot(chatbot)


@router.put("/chatbots/{chatbot_id}")
def update_chatbot(chatbot_id: int, request: ChatbotRequest,
                   service: ChatbotService = Depends(chatbot_service)) -> ChatbotResponse:
    """A changed system prompt gets the next ``prompt_version``."""
    return ChatbotResponse.from_chatbot(service.update_chatbot(chatbot_id, **request.model_dump()))


@router.delete("/chatbots/{chatbot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chatbot(chatbot_id: int, service: ChatbotService = Depends(chatbot_service)) -> Response:
    """With all its conversations; the agent runs stay in Observability."""
    if not service.delete_chatbot(chatbot_id):
        raise NotFoundError(f"Chatbot non trovato: {chatbot_id}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/chatbots/{chatbot_id}/conversations")
def list_conversations(chatbot_id: int,
                       service: ChatbotService = Depends(chatbot_service)) -> list[ConversationResponse]:
    """Most recently updated first."""
    return [ConversationResponse.from_conversation(item) for item in service.list_conversations(chatbot_id)]


@router.post("/chatbots/{chatbot_id}/conversations", status_code=status.HTTP_201_CREATED)
def new_conversation(chatbot_id: int, service: ChatbotService = Depends(chatbot_service)) -> ConversationResponse:
    return ConversationResponse.from_conversation(service.new_conversation(chatbot_id))


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
def send_message(conversation_id: int, request: MessageRequest,
                 service: ChatbotService = Depends(chatbot_service)) -> MessageResponse:
    """Saves the user's message and returns the chatbot's reply (``error`` role
    when the agent could not answer)."""
    return MessageResponse.from_message(service.send(conversation_id, request.text))
