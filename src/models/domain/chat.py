"""Chat models: the catalog of usable LLMs (provider + model id + price),
stored in the DB and edited in Admin → Modelli. Agents, chatbots and pipeline
steps refer to a model by its key ``<provider>/<model id>``."""
from enum import StrEnum
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, StringConstraints


class ModelProvider(StrEnum):
    """Who serves the model. Handle a new one in domain/chat/base.py."""
    OPENROUTER = "openrouter"
    """Main provider: hundreds of models behind one API key (OPENROUTER_API_KEY)."""
    OPENAI = "openai"
    OLLAMA = "ollama"
    """Local models (OLLAMA_URL), free."""
    MOCK = "mock"
    """No LLM: echoes and calls tools on command, to try the flows (domain/chat/mock_client.py)."""


def split_model_key(key: str) -> tuple[ModelProvider, str]:
    """``openrouter/google/gemini-2.5-pro`` → (OPENROUTER, ``google/gemini-2.5-pro``):
    the provider is the part before the first ``/``."""
    provider, _, model = key.strip().partition("/")
    if provider not in set(ModelProvider) or not model:
        raise ValueError(f"modello non valido: {key!r} (atteso <produttore>/<modello>, es. openrouter/google/gemini-2.5-pro)")
    return ModelProvider(provider), model


def _valid_key(key: str) -> str:
    split_model_key(key)
    return key.strip()


ModelKey = Annotated[str, AfterValidator(_valid_key)]
"""A catalog model as ``<provider>/<model id>`` (e.g. ``openai/gpt-4o``)."""


class ChatModel(BaseModel):
    """One model of the catalog. Price in EUR per 1M tokens."""
    provider: ModelProvider
    model: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    """The provider's model id, e.g. ``google/gemini-2.5-pro`` on OpenRouter,
    ``gpt-4o`` on OpenAI, ``mistral:7b`` on Ollama. Also the name datapizza
    reports in its spans, so costs are looked up by it."""
    input_per_1m: float = Field(default=0.0, ge=0)
    output_per_1m: float = Field(default=0.0, ge=0)
    active: bool = True
    """Inactive models cannot be picked nor run (agents using them stop with a clear error)."""

    @property
    def key(self) -> str:
        return f"{self.provider.value}/{self.model}"


class EmbeddingModelName(StrEnum):
    """Embedding models a project can index its RAG data with (``<provider>/<model>``)."""

    OPENAI_TEXT_EMBEDDING_3_SMALL = "openai/text-embedding-3-small"
    OLLAMA_NOMIC_EMBED_TEXT = "ollama/nomic-embed-text"
