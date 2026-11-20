"""Default model catalog (EUR per 1M tokens), seeded into the chat_model table
at startup. Seeding only inserts missing models: edits made in Admin → Modelli win."""
from models.domain.chat import ChatModel, ModelProvider

DEFAULT_CHAT_MODELS: list[ChatModel] = [
    # Cheap and fast, reliable with tools: the one for tests (0.10 / 0.40 USD on OpenRouter).
    ChatModel(provider=ModelProvider.OPENROUTER, model="google/gemini-2.5-flash-lite", input_per_1m=0.09, output_per_1m=0.37),
    ChatModel(provider=ModelProvider.OPENROUTER, model="google/gemini-2.5-pro", input_per_1m=1.15, output_per_1m=9.2),
    ChatModel(provider=ModelProvider.OPENROUTER, model="google/gemini-3.1-flash-lite", input_per_1m=0.23, output_per_1m=1.38),
    # Very cheap, with tools and structured output (OpenRouter, November 2026).
    ChatModel(provider=ModelProvider.OPENROUTER, model="inclusionai/ling-3.0-tiny", input_per_1m=0.014, output_per_1m=0.041),
    ChatModel(provider=ModelProvider.OPENROUTER, model="mistralai/mistral-nemo", input_per_1m=0.027, output_per_1m=0.028),
    ChatModel(provider=ModelProvider.OPENROUTER, model="meta-llama/llama-3.1-8b-instruct", input_per_1m=0.018, output_per_1m=0.037),
    ChatModel(provider=ModelProvider.OPENROUTER, model="openai/gpt-oss-20b", input_per_1m=0.017, output_per_1m=0.083),
    ChatModel(provider=ModelProvider.OPENROUTER, model="tencent/hy4-flash", input_per_1m=0.032, output_per_1m=0.13),
    ChatModel(provider=ModelProvider.OPENROUTER, model="deepseek/deepseek-v4.1-flash", input_per_1m=0.047, output_per_1m=0.19),
    ChatModel(provider=ModelProvider.OPENROUTER, model="openai/gpt-oss-120b", input_per_1m=0.14, output_per_1m=0.55),
    # Cheap but smarter: good candidates for the structured agents (WIP, Pianificatore, Imparato).
    ChatModel(provider=ModelProvider.OPENROUTER, model="openai/gpt-6-luna", input_per_1m=0.09, output_per_1m=0.46),
    ChatModel(provider=ModelProvider.OPENROUTER, model="anthropic/claude-haiku-5.5", input_per_1m=0.09, output_per_1m=0.46),
    ChatModel(provider=ModelProvider.OPENROUTER, model="z-ai/glm-5.3-flash", input_per_1m=0.14, output_per_1m=0.46),
    ChatModel(provider=ModelProvider.OPENAI, model="gpt-5.3", input_per_1m=4.6, output_per_1m=13.8),
    ChatModel(provider=ModelProvider.OPENAI, model="gpt-4o", input_per_1m=3.5, output_per_1m=10.0),
    # Small, for the agents with a structured answer (WIP, Pianificatore, Da riferimenti).
    ChatModel(provider=ModelProvider.OPENAI, model="gpt-4o-mini", input_per_1m=0.14, output_per_1m=0.55),
    ChatModel(provider=ModelProvider.OLLAMA, model="gemma3:4b"),
    ChatModel(provider=ModelProvider.OLLAMA, model="mistral:7b"),
    # No LLM, free: echoes, "/tool name {json}" calls a tool. To try the flows.
    ChatModel(provider=ModelProvider.MOCK, model="echo"),
]
