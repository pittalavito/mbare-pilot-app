"""The coding agent's definition (Copilot's prompts, denied tools and models)
from the data folder: ``definition/global-coding-agent.yml``, whose fields
``definition/project/<slug>/coding-agent.yml`` replaces for its project.
The planning prompts to choose from when delegating are the ``<name>.md`` of
``definition/coding-agent/`` and ``definition/project/<slug>/coding-agent/``
(the project's win by name).

The global file is required: a missing or broken file is an error, never a
fallback to built-in texts (a wrong file must not loosen the denied tools)."""
from typing import Protocol

import yaml
from pydantic import ValidationError as PydanticValidationError

from core.error import ValidationError
from domain.project.data_paths import CODING_AGENT_FILE, CODING_AGENT_PROMPTS_DIR, GLOBAL_CODING_AGENT_FILE, NOTE_SUFFIX, data_file_name, project_definitions
from models.domain.copilot import CodingAgentSettings
from models.domain.definitions import CodingAgentFile

TASK_PLACEHOLDER = "{task}"
_PROMPTS = ("plan_prompt", "execute_prompt")


class DefinitionFiles(Protocol):
    """The files under ``definition/`` (StoreService)."""

    def read_definition(self, path: str) -> str | None: ...

    def list_definitions(self, folder: str) -> list[str]: ...


def load(files: DefinitionFiles, project_name: str | None = None) -> CodingAgentSettings:
    """The global definition, with the project's fields and prompts over it
    (``project_name`` None = only the global one)."""
    values = _values(files, GLOBAL_CODING_AGENT_FILE, "", required=True)
    prompts = _prompts(files, "")
    if project_name is not None:
        folder = project_definitions(project_name)
        values |= _values(files, f"{folder}/{CODING_AGENT_FILE}", folder, required=False)
        prompts |= _prompts(files, folder)
    missing = [name for name in (*_PROMPTS, "denied_tools") if name not in values]
    if missing:
        raise ValidationError(f"definition/{GLOBAL_CODING_AGENT_FILE}: manca {', '.join(missing)}.")
    _check_placeholder("plan_prompt", values["plan_prompt"])
    return CodingAgentSettings(**values, prompts=dict(sorted(prompts.items())))


def plan_prompt(settings: CodingAgentSettings, task: str, prompt: str = "") -> str:
    """The first planning turn with the task's markdown (other braces stay as
    they are); ``prompt`` = one of ``settings.prompts``, ``""`` = ``plan_prompt``."""
    if prompt and prompt not in settings.prompts:
        raise ValidationError(f"Prompt non trovato: {prompt}. Disponibili: {', '.join(settings.prompts) or 'nessuno'}.")
    return (settings.prompts[prompt] if prompt else settings.plan_prompt).replace(TASK_PLACEHOLDER, task.strip())


def check_model(settings: CodingAgentSettings, model: str) -> str:
    """``model`` when it is one of ``settings.models`` (``""`` = the default)."""
    model = model.strip()
    if model and model not in settings.models:
        raise ValidationError(f"Modello non previsto: {model}. Disponibili: {', '.join(settings.models) or 'solo il predefinito'}.")
    return model


def _values(files: DefinitionFiles, path: str, folder: str, required: bool) -> dict:
    """The fields one file sets, prompts read from their files."""
    text = files.read_definition(path)
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
            prompt = _text(files, prompt_path)
            if not prompt:
                raise ValidationError(f"definition/{path}: file del prompt non trovato o vuoto: {prompt_path}")
        if prompt is not None:
            values[name] = prompt
    for name in ("denied_tools", "models"):
        if getattr(spec, name) is not None:
            values[name] = getattr(spec, name)
    return values


def _prompts(files: DefinitionFiles, folder: str) -> dict[str, str]:
    """The ``<name>.md`` of ``<folder>/coding-agent/``: name → text."""
    prompts = {}
    for path in files.list_definitions(f"{folder}/{CODING_AGENT_PROMPTS_DIR}".lstrip("/")):
        name = path.rsplit("/", 1)[-1]
        if not name.lower().endswith(NOTE_SUFFIX):
            continue
        text = _text(files, path)
        if not text:
            raise ValidationError(f"definition/{path}: il prompt è vuoto.")
        _check_placeholder(f"definition/{path}", text)
        prompts[name[: -len(NOTE_SUFFIX)]] = text
    return prompts


def _text(files: DefinitionFiles, path: str) -> str:
    """A prompt file as written, Windows newlines included; "" when missing."""
    return (files.read_definition(path) or "").replace("\r\n", "\n").strip()


def _check_placeholder(where: str, prompt: str) -> None:
    if TASK_PLACEHOLDER not in prompt:
        raise ValidationError(f"{where} deve contenere {TASK_PLACEHOLDER}: è dove va il testo del task.")


def _yaml(path: str, text: str) -> dict | None:
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValidationError(f"definition/{path}: YAML non valido: {exc}") from exc
    if raw is not None and not isinstance(raw, dict):
        raise ValidationError(f"definition/{path}: il file deve contenere dei campi (nome: valore).")
    return raw
