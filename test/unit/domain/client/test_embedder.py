"""The mock embedder of the chatbots' cache: same words = similar, whatever
the case, the accents and the stopwords; deterministic; normalised."""
import math

import pytest

from types import SimpleNamespace

import openai

from core.error import UpstreamError, ValidationError
from domain.client.embedding.embedder import Factory, HashingEmbedder, OpenRouterEmbedder, cosine_similarity


@pytest.fixture
def embedder():
    return HashingEmbedder()


def _similarity(embedder, a, b):
    return cosine_similarity(embedder.embed(a), embedder.embed(b))


def test_case_accents_and_stopwords_do_not_count(embedder):
    assert _similarity(embedder, "Lancia il Report di Città", "lancia report citta") == pytest.approx(1.0)


def test_sharing_words_is_closer_than_not(embedder):
    close = _similarity(embedder, "lancia il report del giorno", "lanciami il report del giorno")
    far = _similarity(embedder, "lancia il report del giorno", "stato dei repository git")

    assert close > 0.5 > far  # 2 words of 3 in common: 0.67


def test_deterministic_normalised_and_named(embedder):
    vector = embedder.embed("report del giorno")

    assert vector == HashingEmbedder().embed("report del giorno")
    assert math.isclose(math.sqrt(sum(v * v for v in vector)), 1.0)
    assert len(vector) == 512 and embedder.name == "hashing-512"
    assert not any(embedder.embed("il di per"))  # only stopwords: all zeros


def test_factory(embedder):
    assert Factory.create("hashing").name == embedder.name
    remote = Factory.create("openrouter/openai/text-embedding-3-small")
    assert remote.name == "openrouter/openai/text-embedding-3-small" and not remote.local and embedder.local
    for name in ("gpt", "openrouter/"):
        with pytest.raises(ValidationError, match="sconosciuto"):
            Factory.create(name)


# ---------------------------------------------------------------- OpenRouter

class _Client:
    """Stands in for openai.OpenAI: records the calls, answers with ``vector`` or raises ``error``."""

    def __init__(self, vector=(3.0, 4.0), error=None):
        self.calls = []
        self.embeddings = SimpleNamespace(create=self._create)
        self._vector, self._error = list(vector), error

    def _create(self, model, input):
        self.calls.append((model, input))
        if self._error:
            raise self._error
        return SimpleNamespace(data=[SimpleNamespace(embedding=self._vector)])


def test_openrouter_vectors_are_normalised():
    client = _Client()

    assert OpenRouterEmbedder("openai/x", client).embed("ciao") == [0.6, 0.8]
    assert client.calls == [("openai/x", ["ciao"])]


def test_openrouter_empty_text_is_not_sent():
    client = _Client()

    assert OpenRouterEmbedder("openai/x", client).embed("  ") == [] and client.calls == []
    assert cosine_similarity([], [0.6, 0.8]) == 0.0


def test_openrouter_errors_become_upstream_errors():
    with pytest.raises(UpstreamError, match="Embedding non riuscito"):
        OpenRouterEmbedder("openai/x", _Client(error=openai.OpenAIError("down"))).embed("ciao")


def test_openrouter_needs_the_key():
    with pytest.raises(ValidationError, match="OPENROUTER_API_KEY"):
        OpenRouterEmbedder("openai/x").embed("ciao")
