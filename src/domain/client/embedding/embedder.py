"""Text embeddings for the chatbots' cache (and, later, the RAG index).

``Embedder`` is the interface, built by ``Factory`` from the configured name
(Config ``CHAT_ROUTE_EMBEDDER``):

- ``hashing``: a mock, no model and no network. Each word (lowercase, no
  accents, no stopwords) is hashed to a fixed position of the vector, so texts
  sharing words are close and synonyms are not.
- ``openrouter/<model>`` (e.g. ``openrouter/openai/text-embedding-3-small``): a
  real model through OpenRouter's embeddings API (OpenAI compatible). The text
  leaves the PC: ``local`` is False, so callers mask it first.

Vectors made by different embedders are not comparable: whoever stores them
keeps the embedder ``name`` alongside."""
import hashlib
import math
import re
import unicodedata
from abc import ABC, abstractmethod

import openai

from config import Config
from core.error import UpstreamError, ValidationError

_WORD = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    "il lo la i gli le un uno una di del dello della dei degli delle a al allo alla ai agli alle da dal dalla "
    "in nel nella con su sul sulla per tra fra e ed o che chi mi ti ci si me te se ne non come".split()
)
_OPENROUTER = "openrouter/"


class Embedder(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        """Stored with every vector: only vectors of the same embedder are compared."""

    @property
    @abstractmethod
    def local(self) -> bool:
        """False when the text is sent outside the PC: callers must mask it first."""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """The text's vector, normalised (length 1; all zeros or empty for a text with no words)."""


class HashingEmbedder(Embedder):

    def __init__(self, dimensions: int = 512):
        self._dimensions = dimensions

    @property
    def name(self) -> str:
        return f"hashing-{self._dimensions}"

    @property
    def local(self) -> bool:
        return True

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self._dimensions
        for word in _words(text):
            digest = hashlib.md5(word.encode("utf-8")).digest()  # stable across processes, unlike hash()
            vector[int.from_bytes(digest[:4], "little") % self._dimensions] += 1.0
        return _normalised(vector)


class OpenRouterEmbedder(Embedder):
    """A model of OpenRouter's embeddings API. The client is built on first use,
    so the app starts without the key (as the chat models)."""

    def __init__(self, model: str, client: openai.OpenAI | None = None):
        """``client``: for tests; by default built from OPENROUTER_API_KEY / OPENROUTER_URL."""
        self._model = model
        self._client = client

    @property
    def name(self) -> str:
        return f"{_OPENROUTER}{self._model}"

    @property
    def local(self) -> bool:
        return False

    def embed(self, text: str) -> list[float]:
        if not text.strip():
            return []
        try:
            response = self._get_client().embeddings.create(model=self._model, input=[text])
        except openai.OpenAIError as exc:
            raise UpstreamError(f"Embedding non riuscito ({self._model} su OpenRouter): {exc}") from exc
        return _normalised(list(response.data[0].embedding))

    def _get_client(self) -> openai.OpenAI:
        if self._client is None:
            config = Config.get()
            key = config.openrouter_api_key.get_secret_value() if config.openrouter_api_key else ""
            if not key:
                raise ValidationError("OPENROUTER_API_KEY is not set: add it to .env to use OpenRouter embeddings.")
            self._client = openai.OpenAI(api_key=key, base_url=config.openrouter_url)
        return self._client


class Factory:

    @staticmethod
    def create(name: str) -> Embedder:
        """The embedder configured as ``name``: ``hashing`` or ``openrouter/<model>``."""
        if name == "hashing":
            return HashingEmbedder()
        if name.startswith(_OPENROUTER) and name.removeprefix(_OPENROUTER):
            return OpenRouterEmbedder(name.removeprefix(_OPENROUTER))
        raise ValidationError(f"Embedder sconosciuto: {name!r} (disponibili: hashing, openrouter/<modello>)")


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Of two normalised vectors of the same length: their dot product (0 for an empty one)."""
    if not a or not b:
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=True))


def _normalised(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector


def _words(text: str) -> list[str]:
    plain = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode("ascii")
    return [word for word in _WORD.findall(plain) if word not in _STOPWORDS]
