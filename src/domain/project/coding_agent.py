"""The coding agent's definition (Copilot's prompts and denied tools) from the
data folder: ``definition/global-coding-agent.yml``, whose fields
``definition/project/<slug>/coding-agent.yml`` replaces for its project.

The global file is required: a missing or broken file is an error, never a
fallback to built-in texts (a wrong file must not loosen the denied tools)."""
from collections.abc import Callable

import yaml
from pydantic import ValidationError as PydanticValidationError

from core.error import ValidationError
from domain.project.data_paths import CODING_AGENT_FILE, GLOBAL_CODING_AGENT_FILE, data_file_name, project_definitions
from models.domain.copilot import CodingAgentSettings
from models.domain.definitions import CodingAgentFile

TASK_PLACEHOLDER = "{task}"
_PROMPTS = ("plan_prompt", "execute_prompt")

Reader = Callable[[str], str | None]
"""A file under ``definition/`` by relative path; None when missing."""


def load(read: Reader, project_name: str | None = None) -> CodingAgentSettings:
    """The global definition, with the project's fields over it (``project_name`` None = only the global one)."""
    values = _values(read, GLOBAL_CODING_AGENT_FILE, "", required=True)
    if project_name is not None:
        folder = project_definitions(project_name)
        values |= _values(read, f"{folder}/{CODING_AGENT_FILE}", folder, required=False)
    missing = [name for name in (*_PROMPTS, "denied_tools") if name not in values]
    if missing:
        raise ValidationError(f"definition/{GLOBAL_CODING_AGENT_FILE}: manca {', '.join(missing)}.")
    if TASK_PLACEHOLDER not in values["plan_prompt"]:
        raise ValidationError(f"plan_prompt deve contenere {TASK_PLACEHOLDER}: è dove va il testo del task.")
    return CodingAgentSettings(**values)


def plan_prompt(settings: CodingAgentSettings, task: str) -> str:
    """The first planning turn with the task's markdown (other braces stay as they are)."""
    return settings.plan_prompt.replace(TASK_PLACEHOLDER, task.strip())


def _values(read: Reader, path: str, folder: str, required: bool) -> dict:
    """The fields one file sets, prompts read from their files."""
    text = read(path)
    raw = _yaml(path, text) if text is not None else None
    if raw is None:
        if required:
            raise ValidationError(f"Manca definition/{path} (prompt e divieti di Copilot): crealo per usare Copilot.")
        return {}
    try:
        spec = CodingAgentFile.model_validate(raw)
    except PydanticValidationError as exc:
        error = exc.errors()[0]
        field = ".".join(str(part) for part in error["loc"])
        raise ValidationError(f"definition/{path}: {field + ': ' if field else ''}{error['msg'].removeprefix('Value error, ')}") from exc
    values: dict = {}
    for name in _PROMPTS:
        prompt, prompt_file = getattr(spec, name), getattr(spec, f"{name}_file")
        if prompt_file is not None:
            prompt_path = f"{folder}/{data_file_name(prompt_file)}".lstrip("/")
            prompt = (read(prompt_path) or "").replace("\r\n", "\n").strip()
            if not prompt:
                raise ValidationError(f"definition/{path}: file del prompt non trovato o vuoto: {prompt_path}")
        if prompt is not None:
            values[name] = prompt
    if spec.denied_tools is not None:
        values["denied_tools"] = spec.denied_tools
    return values


def _yaml(path: str, text: str) -> dict | None:
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValidationError(f"definition/{path}: YAML non valido: {exc}") from exc
    if raw is not None and not isinstance(raw, dict):
        raise ValidationError(f"definition/{path}: il file deve contenere dei campi (nome: valore).")
    return raw
