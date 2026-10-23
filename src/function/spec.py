"""``FunctionSpec``: a Python function a pipeline step can run, with its
parameters declared as a pydantic model (validated on save and before every
run; the step editor builds its form from it)."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from core.error import ValidationError
from function.context import FunctionContext


class NoParams(BaseModel):
    """For functions without parameters."""


@dataclass(frozen=True)
class FunctionSpec:
    name: str
    description: str
    """Shown in the step editor."""
    params: type[BaseModel]
    run: Callable[[FunctionContext, str, Any], str]
    """``run(context, step_input, params)`` → the step output. Raise AppError
    for expected failures (the step fails with that message)."""

    def validate_params(self, raw: dict[str, Any]) -> BaseModel:
        """``raw`` as this function's params; ValidationError naming the field otherwise."""
        try:
            return self.params.model_validate(raw)
        except PydanticValidationError as exc:
            error = exc.errors()[0]
            field = ".".join(str(part) for part in error["loc"]) or "parametri"
            raise ValidationError(f"Funzione {self.name}, parametro {field}: {error['msg']}") from exc

    def execute(self, context: FunctionContext, step_input: str, raw_params: dict[str, Any]) -> str:
        return self.run(context, step_input, self.validate_params(raw_params))
