"""The chatbots' cache: entries the user makes from one of their messages
("this request → that automation, with this input"). A later message similar
enough to an entry launches the automation directly, without running the
chatbot's agent: no LLM, no tokens. The automation then runs in the worker
with its own steps and tools, as always.

Similarity is the cosine of the texts' embeddings (``Embedder``), compared in
Python: a chatbot has few entries. Every comparison is logged (the best
similarities, the threshold, the decision), to tune ``CHAT_ROUTE_THRESHOLD``.

- Same values only: an entry is a candidate only if the message names the same
  sensitive values (the same aliases once masked: ``REPO_7``, ``PERSONA_2``...).
  An embedding finds "git status of REPO_3" closer to "git status of REPO_7"
  than any rewording of it, and the entry's input is fixed: without this rule
  it would launch the automation for the wrong repository. Needs masking.
- An embedder that sends the text outside the PC (``local`` False) only gets it
  masked with the project's map, as an LLM would.
- An entry made by another embedder is embedded again from its text when
  first compared (and saved), so changing ``CHAT_ROUTE_EMBEDDER`` keeps the cache.
- If embedding fails (network, key), the cache is skipped: the agent answers."""
from core.error import AppError, ConflictError, NotFoundError, ValidationError
from core.observability import LogPrefix, log_info, log_warning, observed
from domain.client.embedding.embedder import Embedder, cosine_similarity
from domain.masking.masker import aliases_in
from models.domain.chatbot import ChatRoute, ChatRouteMatch, MessageRole
from models.domain.pipeline import Pipeline, PipelineRun
from service.masking_service import MaskingService, MaskSession
from service.pipeline_service import PipelineService
from service.store_service import StoreService

CACHE_BYPASS = "!"
"""A message starting with it goes to the agent, never to the cache."""
_LOGGED_SCORES = 3
_LOGGED_TEXT = 80


class ChatRouteService:

    def __init__(self, store_service: StoreService, pipeline_service: PipelineService, embedder: Embedder, threshold: float, masking_service: MaskingService | None = None):
        """``masking_service`` is required with an embedder that is not local;
        without it the "same values" rule cannot apply (no aliases)."""
        if not embedder.local and masking_service is None:
            raise ValidationError(f"L'embedder {embedder.name} manda il testo fuori dal PC: serve il mascheramento.")
        self._store = store_service
        self._pipelines = pipeline_service
        self._embedder = embedder
        self._threshold = threshold
        self._masking = masking_service

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
        route = self._store.save_chat_route(ChatRoute(
            chatbot_id=chatbot_id,
            message_id=message_id,
            text=text,
            embedder=self._embedder.name,
            embedding=self._embed(text, self._session(project_name)),
            pipeline_id=pipeline_id,
            pipeline_input=pipeline_input
        ))
        log_info(LogPrefix.CHAT_ROUTE_SERVICE, "Cache chatbot %s · voce %s aggiunta: «%s» → automation %s (%s)", chatbot_id, route.id, _short(text), pipeline_id, self._embedder.name)
        return route

    def remove(self, route_id: int) -> bool:
        return self._store.delete_chat_route(route_id)

    def match(self, chatbot_id: int, text: str) -> ChatRouteMatch | None:
        """The entry most similar to ``text`` among those naming the same
        sensitive values, if at least as similar as the threshold; None also
        when the cache cannot be consulted (logged)."""
        routes = self.routes(chatbot_id)
        if not routes:
            return None
        session = self._session(self._store.get_chatbot(chatbot_id).project_name)
        values = self._values(text, session)
        try:
            embedding = self._embed(text, session)
            scored = sorted(
                (ChatRouteMatch(route=route, similarity=cosine_similarity(embedding, self._current(route, session).embedding))
                 for route in routes),
                key=lambda match: match.similarity, reverse=True,
            )
        except AppError as exc:
            log_warning(LogPrefix.CHAT_ROUTE_SERVICE, "Cache chatbot %s non consultata (%s): risponde l'agente.",
                        chatbot_id, exc)
            return None
        same_values = {match.route.id for match in scored if self._values(match.route.text, session) == values}
        best = next((match for match in scored if match.route.id in same_values), None)
        hit = best is not None and best.similarity >= self._threshold
        log_info(
            LogPrefix.CHAT_ROUTE_SERVICE, "Cache chatbot %s · «%s» · %s · soglia %.2f → %s",
            chatbot_id, _short(session.mask(text) if session else text),
            ", ".join(
                f"voce {match.route.id}={match.similarity:.3f}" + ("" if match.route.id in same_values else " (altri valori)")
                for match in scored[:_LOGGED_SCORES]
            ),
            self._threshold, f"voce {best.route.id}, lancio l'automation" if hit else "nessuna voce, risponde l'agente",
        )
        return best if hit else None

    @observed(LogPrefix.CHAT_ROUTE_SERVICE)
    def launch(self, route: ChatRoute) -> tuple[Pipeline, PipelineRun]:
        """Queue the entry's automation (checked as run_automation does: active,
        with steps) and count the hit."""
        run = self._pipelines.enqueue(route.pipeline_id, route.pipeline_input)
        self._store.save_chat_route(route.model_copy(update={"hits": route.hits + 1}))
        return self._pipelines.get_pipeline(route.pipeline_id), run

    # --------------------------------------------------------------- helpers
    def _session(self, project_name: str) -> MaskSession | None:
        """The project's masking map, loaded once per call (None without masking)."""
        return self._masking.session(project_name) if self._masking is not None else None

    def _embed(self, text: str, session: MaskSession | None) -> list[float]:
        """The text's embedding; masked first when the embedder sends it outside the PC."""
        if not self._embedder.local:
            text = session.mask(text)
        return self._embedder.embed(text)

    @staticmethod
    def _values(text: str, session: MaskSession | None) -> frozenset[str]:
        """The sensitive values a text names, as aliases (with the current map,
        so an entry follows values added to the map after it was made)."""
        return aliases_in(session.mask(text)) if session is not None else frozenset()

    def _current(self, route: ChatRoute, session: MaskSession | None) -> ChatRoute:
        """The entry with an embedding of the configured embedder: one made by
        another embedder is embedded again from its text, and saved."""
        if route.embedder == self._embedder.name:
            return route
        updated = self._store.save_chat_route(route.model_copy(update={
            "embedder": self._embedder.name,
            "embedding": self._embed(route.text, session),
        }))
        log_info(LogPrefix.CHAT_ROUTE_SERVICE, "Cache chatbot %s · voce %s ricalcolata con %s (era %s)",
                 route.chatbot_id, route.id, self._embedder.name, route.embedder)
        return updated


def _short(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= _LOGGED_TEXT else text[:_LOGGED_TEXT - 1] + "…"
