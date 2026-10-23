"""Function registry: the Python functions pipeline steps can run, keyed by name.

A function file under function/list/ declares its ``Params`` (pydantic), a
``run(context, step_input, params) -> str`` and its ``FunctionSpec``; add the
spec here to make it selectable in the step editor.
"""
from core.error import ValidationError
from function.list.git_status import GIT_STATUS
from function.list.save_note import SAVE_NOTE
from function.spec import FunctionSpec

FUNCTION_REGISTRY: dict[str, FunctionSpec] = {
    spec.name: spec
    for spec in (
        GIT_STATUS,
        SAVE_NOTE,
    )
}
"""Every function implemented in code, keyed by name."""


def get_function(name: str | None) -> FunctionSpec:
    if not name:
        raise ValidationError("Scegli la funzione da eseguire.")
    spec = FUNCTION_REGISTRY.get(name)
    if spec is None:
        raise ValidationError(f"La funzione {name} non esiste (più) nel codice.")
    return spec
