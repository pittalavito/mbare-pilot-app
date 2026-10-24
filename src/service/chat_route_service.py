"""The chatbots' cache: entries the user makes from one of their messages
("this request → that automation, with this input"). A later message similar
enough to an entry launches the automation directly, without running the
chatbot's agent: no LLM, no tokens. The automation then runs in the worker
with its own steps and tools, as always.

Similarity is the cosine of the texts' embeddings (``Embedder``), compared in
Python: a chatbot has few entries. Only entries made by the same embedder are
compared."""
from core.error import ConflictError, NotFoundError, ValidationError
from core.observability import LogPrefix, observed
from domain.client.embedding.embedder import Embedder, cosine_similarity
from models.domain.chatbot import ChatRoute, ChatRouteMatch, MessageRole
from models.domain.pipeline import Pipeline, PipelineRun
from service.pipeline_service import PipelineService
from service.store_service import StoreService

CACHE_BYPASS = "!"
"""A message starting with it goes to the agent, never to the cache."""


class ChatRouteService:

    def __init__(self, store_service: StoreService, pipeline_service: PipelineService, embedder: Embedder,
                 threshold: float):
        self._store = store_service
        self._pipelines = pipeline_service
        self._embedder = embedder
        self._threshold = threshold

    def routes(self, chatbot_id: int) -> list[ChatRoute]:
        """A chatbot's entries, oldest first."""
        return self._store.list_chat_routes(chatbot_id)

    @observed(LogPrefix.CHAT_ROUTE_SERVICE)
    def add(self, message_id: int, pipeline_id: int, pipeline_input: str = "") -> ChatRoute:
        """Put a user message in its chatbot's cache, launching ``pipeline_id``
        with ``pipeline_input`` (fixed: the same for every similar message)."""
        message = self._store.get_message(message_id)
        if message is None:
            raise NotFoundError(f"Messaggio non trovato: {message_id}")
        if message.role is not MessageRole.USER:
            raise ValidationError("In cache vanno solo i tuoi messaggi, non le risposte.")
        chatbot_id = self._store.get_conversation(message.conversation_id).chatbot_id
        project_name = self._store.get_chatbot(chatbot_id).project_name
        if self._pipelines.get_pipeline(pipeline_id).project_name != project_name:
            raise ValidationError(f"L'automation non è del progetto {project_name}.")
        if any(route.message_id == message_id for route in self.routes(chatbot_id)):
            raise ConflictError("Questo messaggio è già in cache.")
        text = message.content.removeprefix(CACHE_BYPASS).strip()
        return self._store.save_chat_route(ChatRoute(
            chatbot_id=chatbot_id, message_id=message_id, text=text, embedder=self._embedder.name,
            embedding=self._embedder.embed(text), pipeline_id=pipeline_id, pipeline_input=pipeline_input,
        ))

    def remove(self, route_id: int) -> bool:
        return self._store.delete_chat_route(route_id)

    def match(self, chatbot_id: int, text: str) -> ChatRouteMatch | None:
        """The entry most similar to ``text``, if at least as similar as the threshold."""
        routes = [route for route in self.routes(chatbot_id) if route.embedder == self._embedder.name]
        if not routes:
            return None
        embedding = self._embedder.embed(text)
        best = max((ChatRouteMatch(route=route, similarity=cosine_similarity(embedding, route.embedding))
                    for route in routes), key=lambda match: match.similarity)
        return best if best.similarity >= self._threshold else None

    @observed(LogPrefix.CHAT_ROUTE_SERVICE)
    def launch(self, route: ChatRoute) -> tuple[Pipeline, PipelineRun]:
        """Queue the entry's automation (checked as run_automation does: active,
        with steps) and count the hit."""
        run = self._pipelines.enqueue(route.pipeline_id, route.pipeline_input)
        self._store.save_chat_route(route.model_copy(update={"hits": route.hits + 1}))
        return self._pipelines.get_pipeline(route.pipeline_id), run
