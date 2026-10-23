"""Model catalog (table chat_model), keyed by (provider, model)."""
from sqlalchemy.engine import Engine
from sqlmodel import select

from domain.store.db.repository import SqlRepository
from models.store.db import AgentConfigTable, ChatbotTable, ChatModelTable, PipelineStepTable


class DbChatModelRepository(SqlRepository[ChatModelTable]):

    def __init__(self, engine: Engine):
        super().__init__(engine, ChatModelTable)

    def list_sorted(self) -> list[ChatModelTable]:
        with self._session() as session:
            return list(session.exec(select(ChatModelTable).order_by(ChatModelTable.provider, ChatModelTable.model)).all())

    def keys_in_use(self) -> set[str]:
        """``<provider>/<model>`` keys used by agent configs, chatbots and pipeline steps."""
        with self._session() as session:
            keys = set(session.exec(select(AgentConfigTable.model)).all())
            keys |= set(session.exec(select(ChatbotTable.model)).all())
            keys |= set(session.exec(select(PipelineStepTable.model)).all())
        return {key for key in keys if key}
