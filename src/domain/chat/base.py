"""Chat client factory: builds the datapizza client for a catalog model key
(``<provider>/<model id>``). Clients are built lazily (on first use), so the
app starts without API keys.

OpenRouter and Ollama speak the OpenAI Chat Completions API (OpenAILikeClient);
OpenAI uses its own client (Responses API); ``mock`` is no LLM at all (MockClient)."""
from datapizza.clients.openai import OpenAIClient
from datapizza.clients.openai_like import OpenAILikeClient
from datapizza.core.clients import Client

from config import Config
from core.error import ValidationError
from domain.chat.mock_client import MockClient
from models.domain.chat import ModelProvider, split_model_key


class Factory:

    @staticmethod
    def create_client(model_key: str, temperature: float = 0.1) -> Client:
        """Build the client for ``model_key``. Raises ValidationError when the
        provider is not configured (e.g. missing API key)."""
        config = Config.get()
        try:
            provider, model = split_model_key(model_key)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        if provider is ModelProvider.MOCK:
            return MockClient(model, temperature=temperature)
        if provider is ModelProvider.OPENROUTER:
            return OpenAILikeClient(
                api_key=_require_key(config.openrouter_api_key, "OPENROUTER_API_KEY", "OpenRouter"),
                base_url=config.openrouter_url,
                model=model,
                temperature=temperature,
            )
        if provider is ModelProvider.OPENAI:
            return OpenAIClient(
                api_key=_require_key(config.openai_api_key, "OPENAI_API_KEY", "OpenAI"),
                model=model,
                temperature=temperature,
            )
        return OpenAILikeClient(api_key="ollama", base_url=config.ollama_url, model=model, temperature=temperature)


def _require_key(secret, variable: str, provider: str) -> str:
    value = secret.get_secret_value() if secret else ""
    if not value:
        raise ValidationError(f"{variable} is not set: add it to .env to use {provider} models.")
    return value
