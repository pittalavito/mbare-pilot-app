"""The mock embedder of the chatbots' cache: same words = similar, whatever
the case, the accents and the stopwords; deterministic; normalised."""
import math

import pytest

from core.error import ValidationError
from domain.client.embedding.embedder import Factory, HashingEmbedder, cosine_similarity


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
    with pytest.raises(ValidationError, match="sconosciuto"):
        Factory.create("gpt")
