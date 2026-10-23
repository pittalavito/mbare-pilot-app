"""Token cost from the model catalog (stored in the DB, table chat_model)."""
from models.domain.chat import ChatModel

PriceList = dict[str, ChatModel]
"""Catalog models keyed by model id (the name datapizza reports in its spans)."""


def compute_cost(prices: PriceList, model: str, input_tokens: int, output_tokens: int) -> float:
    """Cost in EUR for the given token usage; 0 for models without a price."""
    pricing = prices.get(model)
    if pricing is None:
        return 0.0

    input_cost = (input_tokens / 1_000_000) * pricing.input_per_1m
    output_cost = (output_tokens / 1_000_000) * pricing.output_per_1m
    return input_cost + output_cost
