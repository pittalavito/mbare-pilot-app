"""Text embeddings for the chatbots' cache (and, later, the RAG index).

``Embedder`` is the interface; ``HashingEmbedder`` the first implementation, a
mock: no model, no network. Each word (lowercase, no accents, no stopwords) is
hashed to a fixed position of the vector, which is then normalised, so texts
sharing words are close and synonyms are not. Real embedders (OpenAI, Ollama)
plug in through ``Factory`` without touching the callers.

Vectors made by different embedders are not comparable: whoever stores them
keeps the embedder ``name`` alongside."""
import hashlib
import math
import re
import unicodedata
from abc import ABC, abstractmethod

from core.error import ValidationError

_WORD = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    "il lo la i gli le un uno una di del dello della dei degli delle a al allo alla ai agli alle da dal dalla "
    "in nel nella con su sul sulla per tra fra e ed o che chi mi ti ci si me te se ne non come".split()
)


class Embedder(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        """Stored with every vector: only vectors of the same embedder are compared."""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """The text's vector, normalised (length 1; all zeros for a text with no words)."""


class HashingEmbedder(Embedder):

    def __init__(self, dimensions: int = 512):
        self._dimensions = dimensions

    @property
    def name(self) -> str:
        return f"hashing-{self._dimensions}"

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self._dimensions
        for word in _words(text):
            digest = hashlib.md5(word.encode("utf-8")).digest()  # stable across processes, unlike hash()
            vector[int.from_bytes(digest[:4], "little") % self._dimensions] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector


class Factory:

    @staticmethod
    def create(name: str) -> Embedder:
        """The embedder configured as ``name`` (Config ``CHAT_ROUTE_EMBEDDER``)."""
        if name == "hashing":
            return HashingEmbedder()
        raise ValidationError(f"Embedder sconosciuto: {name!r} (disponibili: hashing)")


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Of two normalised vectors of the same length: their dot product."""
    return sum(x * y for x, y in zip(a, b, strict=True))


def _words(text: str) -> list[str]:
    plain = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode("ascii")
    return [word for word in _WORD.findall(plain) if word not in _STOPWORDS]
