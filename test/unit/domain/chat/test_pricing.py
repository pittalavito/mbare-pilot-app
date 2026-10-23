import pytest

from domain.chat.pricing import compute_cost
from models.domain.chat import ChatModel, ModelProvider, split_model_key

PRICES = {"gpt-4o": ChatModel(provider=ModelProvider.OPENAI, model="gpt-4o", input_per_1m=3.5, output_per_1m=10.0)}


def test_compute_cost_known_model():
    assert compute_cost(PRICES, "gpt-4o", 1_000_000, 1_000_000) == pytest.approx(13.5)


def test_compute_cost_unknown_model_is_zero():
    assert compute_cost(PRICES, "unknown-model", 1000, 1000) == 0.0


def test_negative_price_rejected():
    with pytest.raises(ValueError):
        ChatModel(provider=ModelProvider.OPENAI, model="x", input_per_1m=-1)


@pytest.mark.parametrize("model", ["", "   "])
def test_empty_model_name_rejected(model):
    with pytest.raises(ValueError):
        ChatModel(provider=ModelProvider.OPENAI, model=model)


def test_model_name_is_stripped_and_key_has_the_provider():
    chat_model = ChatModel(provider="openrouter", model="  google/gemini-2.5-pro ")

    assert chat_model.model == "google/gemini-2.5-pro"
    assert chat_model.key == "openrouter/google/gemini-2.5-pro"
    assert (chat_model.input_per_1m, chat_model.active) == (0.0, True)


@pytest.mark.parametrize("key, expected", [
    ("openrouter/google/gemini-2.5-pro", (ModelProvider.OPENROUTER, "google/gemini-2.5-pro")),
    ("openai/gpt-4o", (ModelProvider.OPENAI, "gpt-4o")),
    ("ollama/mistral:7b", (ModelProvider.OLLAMA, "mistral:7b")),
])
def test_split_model_key(key, expected):
    assert split_model_key(key) == expected


@pytest.mark.parametrize("key", ["gpt-4o", "anthropic/claude", "openai/", ""])
def test_invalid_model_keys(key):
    with pytest.raises(ValueError):
        split_model_key(key)
