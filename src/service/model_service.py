"""The model catalog (Admin → Modelli): which LLMs can be used, from which
provider, at which price. Agents, chatbots and pipeline steps pick their model
from the active ones; ``require_usable_model`` is the check every service runs
before saving or running an agent."""
from core.error import ConflictError, ValidationError
from core.observability import LogPrefix, observed
from models.domain.chat import ChatModel, ModelProvider
from service.store_service import StoreService

_PROVIDER_ORDER = list(ModelProvider)


def require_usable_model(store: StoreService, key: str) -> ChatModel:
    """The catalog model ``key``; ValidationError when missing or inactive."""
    chat_model = store.get_chat_model(key)
    if chat_model is None:
        raise ValidationError(f"Il modello {key} non è nel catalogo: aggiungilo in Admin → Modelli.")
    if not chat_model.active:
        raise ValidationError(f"Il modello {key} è disattivato: riattivalo in Admin → Modelli o scegline un altro.")
    return chat_model


class ModelService:

    def __init__(self, store_service: StoreService):
        self._store = store_service

    def list_models(self, *, active_only: bool = False) -> list[ChatModel]:
        """OpenRouter first (main provider), then OpenAI, then Ollama."""
        models = [model for model in self._store.list_chat_models() if model.active or not active_only]
        return sorted(models, key=lambda model: (_PROVIDER_ORDER.index(model.provider), model.model))

    def choices(self, current: str | None = None) -> list[str]:
        """Keys to offer in a model picker: the active models, plus ``current``
        when it is no longer usable (so an existing agent still shows its model)."""
        keys = [model.key for model in self.list_models(active_only=True)]
        if current and current not in keys:
            keys.append(current)
        return keys

    def seed_defaults(self, seeds: list[ChatModel]) -> int:
        return self._store.seed_chat_models(seeds)

    @observed(LogPrefix.MODEL_SERVICE)
    def save_catalog(self, models: list[ChatModel]) -> list[ChatModel]:
        """Make ``models`` the whole catalog: save them all, delete the others.
        A model still used by an agent, chatbot or pipeline step cannot be
        deleted (deactivate it instead)."""
        keys = [model.key for model in models]
        duplicates = sorted({key for key in keys if keys.count(key) > 1})
        if duplicates:
            raise ValidationError(f"Modelli ripetuti: {', '.join(duplicates)}")
        removed = {model.key for model in self._store.list_chat_models()} - set(keys)
        in_use = sorted(removed & self._store.chat_model_keys_in_use())
        if in_use:
            raise ConflictError(
                f"Non puoi eliminare {', '.join(in_use)}: sono usati da agenti, chatbot o automation. Disattivali invece."
            )
        for model in models:
            self._store.save_chat_model(model)
        for key in removed:
            self._store.delete_chat_model(key)
        return self.list_models()
