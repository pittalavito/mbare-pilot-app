"""Chat endpoints, typed: a project's chatbots, conversations and messages."""
from api_client.http import ApiClient, segment
from api_client.models import Chatbot, Conversation, Message


class ChatApi:

    def __init__(self, client: ApiClient):
        self._client = client

    def chatbots(self, project: str) -> list[Chatbot]:
        return [Chatbot.model_validate(item) for item in self._client.get(f"/projects/{segment(project)}/chatbots")]

    def create_chatbot(self, project: str, body: dict) -> Chatbot:
        """``body``: name, description, system_prompt, model, max_steps, tool_names."""
        return Chatbot.model_validate(self._client.post(f"/projects/{segment(project)}/chatbots", json=body))

    def update_chatbot(self, chatbot_id: int, body: dict) -> Chatbot:
        return Chatbot.model_validate(self._client.put(f"/chatbots/{chatbot_id}", json=body))

    def delete_chatbot(self, chatbot_id: int) -> None:
        self._client.delete(f"/chatbots/{chatbot_id}")

    def conversations(self, chatbot_id: int) -> list[Conversation]:
        """Most recently updated first."""
        return [Conversation.model_validate(item) for item in self._client.get(f"/chatbots/{chatbot_id}/conversations")]

    def new_conversation(self, chatbot_id: int) -> Conversation:
        return Conversation.model_validate(self._client.post(f"/chatbots/{chatbot_id}/conversations"))

    def delete_conversation(self, conversation_id: int) -> None:
        self._client.delete(f"/conversations/{conversation_id}")

    def messages(self, conversation_id: int) -> list[Message]:
        """Oldest first."""
        return [Message.model_validate(item) for item in self._client.get(f"/conversations/{conversation_id}/messages")]

    def send(self, conversation_id: int, text: str) -> Message:
        """Waits for the chatbot's reply."""
        return Message.model_validate(
            self._client.post(f"/conversations/{conversation_id}/messages", json={"text": text}),
        )
