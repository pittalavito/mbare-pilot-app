"""Model catalog: seeds, ordering, saving, usage checks, and the client per provider."""
import pytest
from datapizza.clients.openai import OpenAIClient
from datapizza.clients.openai_like import OpenAILikeClient
from pydantic import SecretStr

from core.error import ConflictError, ValidationError
from domain.chat.base import Factory as ChatFactory
from domain.chat.models_default import DEFAULT_CHAT_MODELS
from models.domain.chat import ChatModel, ModelProvider
from models.domain.chatbot import Chatbot
from models.domain.project import Project, ProjectSource
from service.model_service import ModelService, require_usable_model


@pytest.fixture
def service(catalog_store):
    return ModelService(catalog_store)


def _model(provider, model, **values):
    return ChatModel(provider=provider, model=model, **values)


def test_seeds_are_inserted_once_and_edits_win(service, catalog_store):
    assert {model.key for model in service.list_models()} == {model.key for model in DEFAULT_CHAT_MODELS}
    edited = catalog_store.get_model("openai/gpt-4o").model_copy(update={"input_per_1m": 1.0})
    catalog_store.save_model(edited)

    assert service.seed_defaults(DEFAULT_CHAT_MODELS) == 0
    assert catalog_store.get_model("openai/gpt-4o").input_per_1m == 1.0


def test_openrouter_first_then_openai_then_ollama(service):
    providers = [model.provider for model in service.list_models()]

    assert providers == sorted(providers, key=list(ModelProvider).index)
    assert providers[0] is ModelProvider.OPENROUTER


def test_price_list_is_keyed_by_model_id(catalog_store):
    prices = catalog_store.price_list()

    assert prices["google/gemini-2.5-pro"].provider is ModelProvider.OPENROUTER
    assert prices["gpt-4o"].input_per_1m == 3.5


def test_save_catalog_adds_updates_and_removes(service):
    catalog = service.list_models()
    kept = [model for model in catalog if model.key != "ollama/gemma3:4b"]
    added = _model("openrouter", "anthropic/claude-sonnet-4.5", input_per_1m=2.8, output_per_1m=13.9)

    saved = service.save_catalog([*kept, added])

    keys = {model.key for model in saved}
    assert "openrouter/anthropic/claude-sonnet-4.5" in keys and "ollama/gemma3:4b" not in keys


def test_duplicates_rejected(service):
    model = _model("openai", "gpt-4o")

    with pytest.raises(ValidationError, match="ripetuti"):
        service.save_catalog([model, model])


def test_model_in_use_cannot_be_deleted_only_deactivated(service, project_store, chatbot_store):
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path="/code/acme"))
    chatbot_store.save_chatbot(Chatbot(project_name="acme", name="Bot", system_prompt="x", model="ollama/mistral:7b"))
    without = [model for model in service.list_models() if model.key != "ollama/mistral:7b"]

    with pytest.raises(ConflictError, match="ollama/mistral:7b"):
        service.save_catalog(without)

    deactivated = [model.model_copy(update={"active": model.key != "ollama/mistral:7b"}) for model in service.list_models()]
    service.save_catalog(deactivated)
    assert "ollama/mistral:7b" not in service.choices()
    assert service.choices(current="ollama/mistral:7b")[-1] == "ollama/mistral:7b"


def test_require_usable_model(catalog_store):
    assert require_usable_model(catalog_store, "openai/gpt-4o").model == "gpt-4o"
    with pytest.raises(ValidationError, match="non è nel catalogo"):
        require_usable_model(catalog_store, "openrouter/x/unknown")
    catalog_store.save_model(_model("openai", "gpt-4o", active=False))
    with pytest.raises(ValidationError, match="disattivato"):
        require_usable_model(catalog_store, "openai/gpt-4o")


# ----------------------------------------------------------------- clients

def test_client_per_provider(config):
    from config import Config
    Config.set(config.model_copy(update={"openrouter_api_key": SecretStr("or-key")}))

    openrouter = ChatFactory.create_client("openrouter/google/gemini-2.5-pro")
    openai = ChatFactory.create_client("openai/gpt-4o")
    ollama = ChatFactory.create_client("ollama/mistral:7b")

    assert isinstance(openrouter, OpenAILikeClient) and openrouter.model_name == "google/gemini-2.5-pro"
    assert str(openrouter.base_url).startswith("https://openrouter.ai/api/v1")
    assert isinstance(openai, OpenAIClient) and openai.model_name == "gpt-4o"
    assert isinstance(ollama, OpenAILikeClient) and ollama.model_name == "mistral:7b"


def test_missing_openrouter_key_explains_it():
    with pytest.raises(ValidationError, match="OPENROUTER_API_KEY"):
        ChatFactory.create_client("openrouter/google/gemini-2.5-pro")


def test_unknown_provider_rejected():
    with pytest.raises(ValidationError, match="modello non valido"):
        ChatFactory.create_client("anthropic/claude")
