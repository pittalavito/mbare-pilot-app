"""The coding agent's definition (Copilot's prompts, denied tools and models)
from the data folder: ``definition/global-coding-agent.yml``, whose fields
``definition/project/<slug>/coding-agent.yml`` replaces for its project.
The planning prompts to choose from when delegating are the ``<name>.md`` of
``definition/coding-agent/`` and ``definition/project/<slug>/coding-agent/``
(the project's win by name); ``type_prompts`` picks one per task type when
the user does not choose; ``task_checklists`` say, per task type, what a
refined task should have (the Refiner checks it). Every planning prompt says where the task is with
``{task_folder}``: the task and its references are files in the repository
(domain/project/task_folder.py), not text of the prompt. The drafts' templates
(blocco 10) are ``coding-agent/templates/<type>.md`` (``confluence.md``,
``jira.md``; the project's win by name): a prompt puts the template of the
task's type where it writes ``{template}``.

The global file is required: a missing or broken file is an error, never a
fallback to built-in texts (a wrong file must not loosen the denied tools)."""
from typing import Protocol

import yaml
from pydantic import ValidationError as PydanticValidationError

from core.error import ValidationError
from domain.project.data_paths import CODING_AGENT_FILE, CODING_AGENT_PROMPTS_DIR, GLOBAL_CODING_AGENT_FILE, NOTE_SUFFIX, data_file_name, project_definitions
from models.domain.copilot import CodingAgentSettings, CopilotModel, CopilotPrice
from models.domain.definitions import CodingAgentFile, ModelFile
from models.domain.note import TaskType

TASK_FOLDER_PLACEHOLDER = "{task_folder}"
TEMPLATE_PLACEHOLDER = "{template}"
TEMPLATES_DIR = "templates"
_PROMPTS = ("plan_prompt", "execute_prompt")


class DefinitionFiles(Protocol):
    """The files under ``definition/`` (DefinitionStore)."""

    def read_definition(self, path: str) -> str | None: ...

    def list_definitions(self, folder: str) -> list[str]: ...


def load(files: DefinitionFiles, project_name: str | None = None) -> CodingAgentSettings:
    """The global definition, with the project's fields and prompts over it
    (``project_name`` None = only the global one)."""
    values = _values(files, GLOBAL_CODING_AGENT_FILE, "", required=True)
    prompts, templates = _prompts(files, ""), _templates(files, "")
    if project_name is not None:
        folder = project_definitions(project_name)
        values |= _values(files, f"{folder}/{CODING_AGENT_FILE}", folder, required=False)
        prompts |= _prompts(files, folder)
        templates |= _templates(files, folder)
    missing = [name for name in (*_PROMPTS, "denied_tools") if name not in values]
    if missing:
        raise ValidationError(f"definition/{GLOBAL_CODING_AGENT_FILE}: manca {', '.join(missing)}.")
    _check_placeholder("plan_prompt", values["plan_prompt"])
    unknown = sorted({name for name in values.get("type_prompts", {}).values() if name and name not in prompts})
    if unknown:
        raise ValidationError(f"type_prompts: prompt non trovati: {', '.join(unknown)}. "
                              f"Disponibili: {', '.join(sorted(prompts)) or 'nessuno'} (i file .md di coding-agent/).")
    return CodingAgentSettings(**values, prompts=dict(sorted(prompts.items())), templates=templates)


def task_prompt(settings: CodingAgentSettings, task_type: TaskType, prompt: str = "") -> str:
    """The planning prompt to use: ``prompt`` when chosen, else the one of the
    task's type (``""`` = ``plan_prompt``)."""
    return prompt.strip() or settings.type_prompts.get(task_type, "")


def plan_prompt(settings: CodingAgentSettings, task_folder: str, prompt: str = "", task_type: TaskType | None = None) -> str:
    """The first planning turn, ``{task_folder}`` = where the task is in the
    repository (other braces stay as they are); ``prompt`` = one of
    ``settings.prompts``, ``""`` = ``plan_prompt``."""
    if prompt and prompt not in settings.prompts:
        raise ValidationError(f"Prompt non trovato: {prompt}. Disponibili: {', '.join(settings.prompts) or 'nessuno'}.")
    text = (settings.prompts[prompt] if prompt else settings.plan_prompt).replace(TASK_FOLDER_PLACEHOLDER, task_folder)
    template = settings.templates.get(task_type, "") if task_type is not None else ""
    return text.replace(TEMPLATE_PLACEHOLDER, template or "(nessun template: scegli tu le sezioni)")


def task_checklist(settings: CodingAgentSettings, task_type: TaskType) -> list[str]:
    """What a refined task of ``task_type`` should have (``[]`` = nothing written)."""
    return list(settings.task_checklists.get(task_type, []))


def check_model(settings: CodingAgentSettings, model: str) -> str:
    """``model`` when it is one of ``settings.models`` (``""`` = the default)."""
    model = model.strip()
    names = [item.name for item in settings.models]
    if model and model not in names:
        raise ValidationError(f"Modello non previsto: {model}. Disponibili: {', '.join(names) or 'solo il predefinito'}.")
    return model


def _values(files: DefinitionFiles, path: str, folder: str, required: bool) -> dict:
    """The fields one file sets, prompts read from their files."""
    text = files.read_definition(path)
    raw = _yaml(path, text) if text is not None else None
    if raw is None:
        if required:
            raise ValidationError(f"Manca definition/{path} (prompt e divieti di Copilot): crealo per usare Copilot "
                                  "(un esempio: python resource/scripts/init-definitions.py).")
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
    if spec.denied_tools is not None:
        values["denied_tools"] = spec.denied_tools
    if spec.type_prompts is not None:
        values["type_prompts"] = {kind: name.strip() for kind, name in spec.type_prompts.items()}
    if spec.task_checklists is not None:
        values["task_checklists"] = {kind: list(points) for kind, points in spec.task_checklists.items()}
    if spec.models is not None:
        values["models"] = [_model(item) for item in spec.models]
        names = [model.name for model in values["models"]]
        if duplicated := sorted({name for name in names if names.count(name) > 1}):
            raise ValidationError(f"definition/{path}: modelli ripetuti in models: {', '.join(duplicated)}")
    return values


def _model(item: ModelFile) -> CopilotModel:
    """An element of ``models:``, with its price when it has one."""
    price = lambda tier: CopilotPrice(input=tier.input, cached_input=tier.cached_input or 0.0, cache_write=tier.cache_write, output=tier.output)  # noqa: E731
    return CopilotModel(
        name=item.name, note=item.note.strip(),
        price=price(item) if item.input is not None else None,
        long_context_above=item.long_context.above if item.long_context else None,
        long_context_price=price(item.long_context) if item.long_context else None,
    )


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


def _templates(files: DefinitionFiles, folder: str) -> dict[TaskType, str]:
    """The ``<type>.md`` of ``<folder>/coding-agent/templates/``: task type → text (other names are ignored)."""
    templates = {}
    for path in files.list_definitions(f"{folder}/{CODING_AGENT_PROMPTS_DIR}/{TEMPLATES_DIR}".lstrip("/")):
        name = path.rsplit("/", 1)[-1]
        stem = name[: -len(NOTE_SUFFIX)] if name.lower().endswith(NOTE_SUFFIX) else ""
        if stem in {kind.value for kind in TaskType} and (text := _text(files, path)):
            templates[TaskType(stem)] = text
    return templates


def _text(files: DefinitionFiles, path: str) -> str:
    """A prompt file as written, Windows newlines included; "" when missing."""
    return (files.read_definition(path) or "").replace("\r\n", "\n").strip()


def _check_placeholder(where: str, prompt: str) -> None:
    if TASK_FOLDER_PLACEHOLDER not in prompt:
        raise ValidationError(f"{where} deve contenere {TASK_FOLDER_PLACEHOLDER}: è la cartella con il task e i suoi riferimenti.")


def _yaml(path: str, text: str) -> dict | None:
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValidationError(f"definition/{path}: YAML non valido: {exc}") from exc
    if raw is not None and not isinstance(raw, dict):
        raise ValidationError(f"definition/{path}: il file deve contenere dei campi (nome: valore).")
    return raw
