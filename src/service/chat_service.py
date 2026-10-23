from datapizza.core.clients import Client

from domain.chat.base import Factory as ChatFactory


class ChatService:

    def __init__(self):
        self._clients: dict[str, Client] = {}

    def get_client(self, model_key: str) -> Client:
        """The client for the catalog model ``model_key`` (``<provider>/<model>``),
        built on first use and then reused."""
        if model_key not in self._clients:
            self._clients[model_key] = ChatFactory.create_client(model_key)
        return self._clients[model_key]
