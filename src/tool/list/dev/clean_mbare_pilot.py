"""clean_mbare_pilot («Verifica sviluppo»): what the app left in the
repository for Copilot goes away before the tests:

- the task's folder ``mbare-pilot/<task>/`` (and ``mbare-pilot/`` when empty);
- the ``todoMbarePilot{...}`` comments in the **changed files** (the ones
  Copilot touched, from ``git status``): a line that is only such a comment
  is removed; one that also holds code stays, and the text says where.

The changes stay uncommitted. ``target`` is ``<repository> <task> [all|touched]``
(domain/dev/inputs.py): in the automation, the run input."""
from pathlib import Path

from pydantic import BaseModel, Field

from domain.dev.inputs import ROOT, parse_verify
from domain.project import code_todos, task_folder
from models.domain.git import GitChangeKind
from models.domain.masking import MaskRepositoryName
from tool.context import ToolContext
from tool.spec import params_tool


class Params(BaseModel):
    target: str = Field(..., description="«<repository> <task> [all|touched]» (. = the project folder), e.g. 'api agent-task-login.md touched'.")
    remove_todos: bool = Field(True, description="Togli anche i commenti todoMbarePilot dai file cambiati.")


class Result(BaseModel):
    text: str
    repository: MaskRepositoryName


def run(context: ToolContext, params: Params) -> Result:
    project = context.require_project()
    repository, task, _ = parse_verify(params.target)
    root = context.git.repository_folder(project, repository)
    lines = ["Pulizia:", f"- cartella {task_folder.relative_folder(task)}: " + ("tolta" if task_folder.remove(root, task) else "non c'era")]
    if params.remove_todos:
        lines += _todos(context, project, repository, root)
    return Result(text="\n".join(lines), repository=repository or ROOT)


def _todos(context: ToolContext, project: str, repository: str, root: Path) -> list[str]:
    changed = [change.path for change in context.git.status(project, repository).changes
               if change.kind is not GitChangeKind.DELETED and not task_folder.is_task_path(change.path)]
    removed, mixed = 0, []
    for path in changed:
        file = root / path
        try:
            with file.open(encoding="utf-8", newline="") as handle:  # line endings as they are (no CRLF ↔ LF)
                text = handle.read()
        except (OSError, UnicodeDecodeError):  # a binary or unreadable file has no comments to remove
            continue
        cleaned, count, left = code_todos.strip(text)
        if count:
            with file.open("w", encoding="utf-8", newline="") as handle:
                handle.write(cleaned)
            removed += count
        mixed += [f"{path}:{number}" for number in left]
    found = [f"- commenti {code_todos.MARKER}: " + (f"tolti {removed}" if removed else "nessuno nei file cambiati")]
    if mixed:
        found.append(f"- da togliere a mano (sulla riga c'è anche codice): {', '.join(mixed)}")
    return found


CLEAN_MBARE_PILOT = params_tool(
    "clean_mbare_pilot",
    "Removes the task's mbare-pilot folder and the todoMbarePilot comments from the changed files (the first step of «Verifica sviluppo»).",
    Params, run, writes=True,
)
