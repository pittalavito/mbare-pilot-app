"""The catalogs: chat models (``chat_model``) and tools (``tool``), domain <-> rows."""
from models.domain.agent import ToolInfo
from models.domain.chat import ChatModel
from models.store.db import ChatModelTable, ToolTable


class Adapter:
    """Read seam: DB rows -> domain models."""

    @staticmethod
    def to_chat_model(row: ChatModelTable) -> ChatModel:
        return ChatModel.model_validate(row.model_dump())

    @staticmethod
    def to_tool(row: ToolTable, available: bool) -> ToolInfo:
        return ToolInfo(name=row.name, description=row.description, available=available)


class Factory:
    """Write seam: domain models -> DB rows."""

    @staticmethod
    def to_chat_model_row(chat_model: ChatModel) -> ChatModelTable:
        return ChatModelTable(**{**chat_model.model_dump(), "provider": chat_model.provider.value})

    @staticmethod
    def to_tool_row(tool: ToolInfo) -> ToolTable:
        return ToolTable(name=tool.name, description=tool.description)
