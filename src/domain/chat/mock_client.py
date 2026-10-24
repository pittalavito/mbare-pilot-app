"""A mock chat model (catalog key ``mock/<anything>``) to try the app's flows
without a real LLM: chatbot, agents, automations, tools. Free and offline.

- It echoes its input: ``[mock] <input>``.
- ``/tool <name> {json arguments}`` anywhere in the input calls that tool of
  the agent (arguments optional, ``{}`` by default); on the next step, once the
  tool has answered, it replies with the tool's result.
- Tokens are estimated as words (system prompt + memory + input; output), so
  Observability fills up; the catalog price is 0.
"""
import json
import re
import uuid
from collections.abc import AsyncIterator, Iterator

from datapizza.core.clients import Client
from datapizza.core.clients.models import ClientResponse, TokenUsage
from datapizza.memory import Memory
from datapizza.tools import Tool
from datapizza.type import Block, FunctionCallBlock, FunctionCallResultBlock, TextBlock

PREFIX = "[mock]"
_TOOL_COMMAND = re.compile(r"/tool\s+([\w-]+)\s*(\{.*\})?", re.DOTALL)


class MockClient(Client):

    def __init__(self, model: str, temperature: float | None = None):
        super().__init__(model_name=model, system_prompt="", temperature=temperature)

    def _invoke(self, input: list[Block], tools: list[Tool] | None = None, memory: Memory | None = None,
                tool_choice: str = "auto", temperature: float | None = None, max_tokens: int | None = None,
                system_prompt: str | None = None, **kwargs) -> ClientResponse:
        text = _text(input)
        results = _last_tool_results(memory)
        if results:
            content: list[Block] = [TextBlock(content=f"{PREFIX} " + "\n".join(
                f"{result.tool.name} → {result.result}" for result in results))]
        elif command := _TOOL_COMMAND.search(text):
            content = [_tool_call(command, tools or [])]
        else:
            content = [TextBlock(content=f"{PREFIX} {text}".rstrip())]
        prompt = " ".join([system_prompt or "", _memory_text(memory), text])
        usage = TokenUsage(prompt_tokens=_words(prompt), completion_tokens=_words(_text(content)))
        return ClientResponse(content=content, stop_reason="stop", usage=usage)

    async def _a_invoke(self, input: list[Block], tools: list[Tool] | None = None, memory: Memory | None = None,
                        tool_choice: str = "auto", temperature: float | None = None, max_tokens: int | None = None,
                        system_prompt: str | None = None, **kwargs) -> ClientResponse:
        return self._invoke(input, tools, memory, tool_choice, temperature, max_tokens, system_prompt, **kwargs)

    def _stream_invoke(self, input: list[Block], tools: list[Tool] | None = None, memory: Memory | None = None,
                       tool_choice: str = "auto", temperature: float | None = None, max_tokens: int | None = None,
                       system_prompt: str | None = None, **kwargs) -> Iterator[ClientResponse]:
        yield self._invoke(input, tools, memory, tool_choice, temperature, max_tokens, system_prompt, **kwargs)

    async def _a_stream_invoke(self, input: list[Block], tools: list[Tool] | None = None, memory: Memory | None = None,
                               tool_choice: str = "auto", temperature: float | None = None,
                               max_tokens: int | None = None, system_prompt: str | None = None,
                               **kwargs) -> AsyncIterator[ClientResponse]:
        yield self._invoke(input, tools, memory, tool_choice, temperature, max_tokens, system_prompt, **kwargs)

    def _structured_response(self, *args, **kwargs) -> ClientResponse:
        raise NotImplementedError("Il modello mock non produce risposte strutturate.")

    async def _a_structured_response(self, *args, **kwargs) -> ClientResponse:
        raise NotImplementedError("Il modello mock non produce risposte strutturate.")

    def _convert_tool_choice(self, tool_choice: str | list[str]) -> dict:
        return {}


def _tool_call(command: re.Match, tools: list[Tool]) -> Block:
    """The call of the tool named in ``/tool``, or a text saying why it cannot be made."""
    name, raw_arguments = command.group(1), command.group(2) or "{}"
    tool = next((candidate for candidate in tools if candidate.name == name), None)
    if tool is None:
        available = ", ".join(candidate.name for candidate in tools) or "nessuno"
        return TextBlock(content=f"{PREFIX} tool {name} non disponibile (tool dell'agente: {available}).")
    try:
        arguments = json.loads(raw_arguments)
    except json.JSONDecodeError as exc:
        return TextBlock(content=f"{PREFIX} argomenti di {name} non validi (JSON): {exc.msg}.")
    return FunctionCallBlock(id=f"mock-{uuid.uuid4().hex[:8]}", arguments=arguments, name=name, tool=tool)


def _last_tool_results(memory: Memory | None) -> list[FunctionCallResultBlock]:
    """The tool results at the end of the memory: the agent's step right after a call."""
    results = []
    for turn in reversed(list(memory or [])):
        blocks = [block for block in turn if isinstance(block, FunctionCallResultBlock)]
        if not blocks:
            break
        results = blocks + results
    return results


def _text(blocks: list[Block]) -> str:
    return " ".join(block.content for block in blocks if isinstance(block, TextBlock)).strip()


def _memory_text(memory: Memory | None) -> str:
    return " ".join(_text(list(turn)) for turn in memory or [])


def _words(text: str) -> int:
    return len(text.split())
