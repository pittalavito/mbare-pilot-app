"""``ToolSpec``: how the registry knows a tool without building it."""
from collections.abc import Callable
from dataclasses import dataclass

from datapizza.tools import Tool

from tool.context import ToolContext


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    """Shown in the catalog (the built tool carries its own for the LLM)."""
    build: Callable[[ToolContext], Tool]
    """Builds the tool for one run, closing over what it needs from the context."""
    chatbot_only: bool = False
    """Works only in a chatbot's run: the UI offers it only to chatbots."""


def static(implementation: Tool) -> ToolSpec:
    """Spec of a tool that needs nothing from the run."""
    return ToolSpec(implementation.name, implementation.description or "", lambda context: implementation)
