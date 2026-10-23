"""Default model catalog (EUR per 1M tokens), seeded into the chat_model table
at startup. Seeding only inserts missing models: edits made in Admin → Modelli win."""
from models.domain.chat import ChatModel, ModelProvider

DEFAULT_CHAT_MODELS: list[ChatModel] = [
    # Cheap and fast, reliable with tools: the one for tests (0.10 / 0.40 USD on OpenRouter).
    ChatModel(provider=ModelProvider.OPENROUTER, model="google/gemini-2.5-flash-lite", input_per_1m=0.09, output_per_1m=0.35),
    ChatModel(provider=ModelProvider.OPENROUTER, model="google/gemini-2.5-pro", input_per_1m=1.15, output_per_1m=9.2),
    ChatModel(provider=ModelProvider.OPENROUTER, model="google/gemini-3.1-flash-lite-preview", input_per_1m=0.07, output_per_1m=0.28),
    ChatModel(provider=ModelProvider.OPENAI, model="gpt-5.3", input_per_1m=4.6, output_per_1m=13.8),
    ChatModel(provider=ModelProvider.OPENAI, model="gpt-4o", input_per_1m=3.5, output_per_1m=10.0),
    ChatModel(provider=ModelProvider.OLLAMA, model="gemma3:4b"),
    ChatModel(provider=ModelProvider.OLLAMA, model="mistral:7b"),
]
