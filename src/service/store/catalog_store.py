"""The catalogs agents are built from: the chat models (with their prices) and
the tools. Agents, chatbots and pipeline steps refer to them by key, so the
store also knows which models are still in use."""
from sqlalchemy.engine import Engine

from domain.chat.pricing import PriceList
from domain.store.db.catalog_mapper import Adapter, Factory
from domain.store.db.chat_model_repository import DbChatModelRepository
from domain.store.db.tool_repository import DbToolRepository
from models.domain.agent import ToolInfo
from models.domain.chat import ChatModel


class CatalogStore:

    def __init__(self, engine: Engine):
        self._chat_models = DbChatModelRepository(engine)
        self._tools = DbToolRepository(engine)

    # ----------------------------------------------------------- chat models
    def seed_models(self, seeds: list[ChatModel]) -> int:
        """Insert the seed models not in the catalog yet. Returns how many."""
        return self._chat_models.insert_missing([Factory.to_chat_model_row(seed) for seed in seeds])

    def list_models(self) -> list[ChatModel]:
        """Sorted by provider and model id."""
        return [Adapter.to_chat_model(row) for row in self._chat_models.list_sorted()]

    def get_model(self, key: str) -> ChatModel | None:
        """By ``<provider>/<model>`` key; None when not in the catalog."""
        provider, _, model = key.partition("/")
        row = self._chat_models.get((provider, model))
        return Adapter.to_chat_model(row) if row else None

    def price_list(self) -> PriceList:
        """Keyed by model id, as datapizza names models in its spans."""
        return {chat_model.model: chat_model for chat_model in self.list_models()}

    def save_model(self, chat_model: ChatModel) -> ChatModel:
        return Adapter.to_chat_model(self._chat_models.save(Factory.to_chat_model_row(chat_model)))

    def delete_model(self, key: str) -> bool:
        provider, _, model = key.partition("/")
        return self._chat_models.delete((provider, model))

    def model_keys_in_use(self) -> set[str]:
        """Models referenced by agent configs, chatbots or pipeline steps. The
        query reads their tables, but the question is the catalog's: which
        models cannot be deleted."""
        return self._chat_models.keys_in_use()

    # ----------------------------------------------------------------- tools
    def list_tools(self, implemented: set[str]) -> list[ToolInfo]:
        """The catalog; ``available`` tells whether each tool is in ``implemented``."""
        return [Adapter.to_tool(row, available=row.name in implemented) for row in self._tools.list_sorted()]

    def sync_tools(self, tools: list[ToolInfo]) -> None:
        """Upsert the tools implemented in code (name + description). Catalog
        rows of tools no longer in code are kept, so old configs stay readable."""
        for tool in tools:
            self._tools.save(Factory.to_tool_row(tool))
