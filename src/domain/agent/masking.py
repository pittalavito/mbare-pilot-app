"""The masking of an agent run: the one place where values are masked for an LLM.

Everything that reaches the model passes here: the task input, the
conversation, the tools' output. Everything that comes back is unmasked here
before it is saved and shown: the answer, the tools' arguments. Sensitive values
enter the project's map from here too: the repository names the project has,
and the ones declared by the tools' output models (``models.domain.masking``).

The session is any object with the ``MaskSession`` methods (see ``Masking``):
without one (no project) the run goes through unchanged, tools' output still
serialized. Tools return their output model; ``wrap`` serializes it, so the
model never sees a Python object."""
import copy
from collections import defaultdict
from typing import Any, Protocol

from datapizza.tools import Tool
from pydantic import BaseModel

from models.domain.chatbot import ChatMessage
from models.domain.masking import MaskCategory, sensitive_values


class Masking(Protocol):
    """What an agent run needs from a project's masking (``MaskSession``)."""

    def mask(self, text: str) -> str: ...

    def unmask(self, text: str) -> str: ...

    def unmask_value(self, value: Any) -> Any: ...

    def register_all(self, category: MaskCategory, values: list[str]) -> None: ...


class AgentMask:

    def __init__(self, session: Masking | None, repositories: list[str] = ()):
        """``repositories``: the project's repository paths, masked from the first
        message on (not only once a tool reads them)."""
        self._session = session
        if session is not None and repositories:
            session.register_all(MaskCategory.REPOSITORY, list(repositories))

    def input(self, text: str) -> str:
        return self._session.mask(text) if self._session else text

    def history(self, messages: list[ChatMessage] | None) -> list[ChatMessage]:
        if self._session is None:
            return list(messages or [])
        return [message.model_copy(update={"content": self._session.mask(message.content)}) for message in messages or []]

    def answer(self, text: str) -> str:
        return self._session.unmask(text) if self._session else text

    def wrap(self, tools: list[Tool]) -> list[Tool]:
        """Copies of the tools (the static ones are shared): arguments come in
        unmasked, the output goes to the model serialized, its sensitive values
        registered and masked."""
        return [self._wrapped(tool) for tool in tools]

    def _wrapped(self, tool: Tool) -> Tool:
        original = tool.func

        def run(*args, **kwargs):
            if self._session is not None:
                args, kwargs = self._session.unmask_value(args), self._session.unmask_value(kwargs)
            text = self._output_text(original(*args, **kwargs))
            return self._session.mask(text) if self._session is not None else text

        wrapped = copy.copy(tool)
        wrapped.func = run
        return wrapped

    def _output_text(self, result: Any) -> str:
        if isinstance(result, BaseModel):
            self._register(result)
            return result.model_dump_json()
        return result

    def _register(self, result: BaseModel) -> None:
        if self._session is None:
            return
        by_category: dict[MaskCategory, list[str]] = defaultdict(list)
        for category, value in sensitive_values(result):
            by_category[category].append(value)
        for category, values in by_category.items():
            self._session.register_all(category, values)
