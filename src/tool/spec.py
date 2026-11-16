"""``ToolSpec``: how the registry knows a tool without building it.

Two ways to write a tool: a function decorated with datapizza's ``@tool``
(its signature is the schema), or ``params_tool``: a pydantic ``Params`` model
(validated, with defaults, the editor's form) and ``run(context, params)``.
A tool's result may carry a ``text`` field: what an automation step outputs
(the rest goes to an agent as JSON)."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from datapizza.tools import Tool
from pydantic import BaseModel, ValidationError as PydanticValidationError

from core.error import AppError
from tool.context import ToolContext


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    """Shown in the catalog (the built tool carries its own for the LLM)."""
    build: Callable[[ToolContext], Tool]
    """Builds the tool for one run, closing over what it needs from the context."""
    chatbot_only: bool = False
    """Works only in a chatbot's run: the UI offers it only to chatbots, an automation step cannot use it."""
    writes: bool = False
    """Changes something (files, git, notes, commands): «Prova» in Admin asks before running it."""

    def schema(self) -> tuple[dict[str, dict[str, Any]], list[str]]:
        """The arguments (JSON schema properties) and the required ones, without a run."""
        built = self.build(_SCHEMA_CONTEXT)
        return dict(built.properties or {}), list(built.required or [])


_SCHEMA_CONTEXT = ToolContext(project_name=None, git=None)  # type: ignore[arg-type]
"""Only to read a tool's schema: building a tool never uses its context."""


def static(implementation: Tool) -> ToolSpec:
    """Spec of a tool that needs nothing from the run."""
    return ToolSpec(implementation.name, implementation.description or "", lambda context: implementation)


def params_tool[ParamsT: BaseModel](name: str, description: str, params: type[ParamsT], run: Callable[[ToolContext, ParamsT], BaseModel], *,
                                    writes: bool = False, chatbot_only: bool = False) -> ToolSpec:
    """A tool whose arguments are ``params``' fields. A wrong argument or an
    AppError comes back to the caller as ``ToolErrorResponse`` (an agent can
    retry; a step fails with it), with the project's local paths hidden."""
    properties, required = _schema(params)

    def build(context: ToolContext) -> Tool:
        def call(**arguments: Any) -> BaseModel:
            from models.domain.tool import ToolErrorResponse
            from tool.list.git.errors import git_error  # the git tools' helper: local paths hidden, repositories listed
            try:
                values = params.model_validate(arguments)
            except PydanticValidationError as exc:
                error = exc.errors()[0]
                where = ".".join(str(part) for part in error["loc"]) or "argomenti"
                return ToolErrorResponse(error=f"{name}, {where}: {error['msg']}")
            try:
                return run(context, values)
            except AppError as exc:
                return git_error(context, exc)

        return Tool(func=call, name=name, description=description, properties=properties, required=required, strict=False)

    return ToolSpec(name=name, description=description, build=build, writes=writes, chatbot_only=chatbot_only)


def _schema(params: type[BaseModel]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """The model's fields as JSON schema properties (titles dropped); none is required: each has a default."""
    raw = params.model_json_schema()
    properties = {name: {key: value for key, value in field.items() if key != "title"} for name, field in raw.get("properties", {}).items()}
    return properties, list(raw.get("required", []))
