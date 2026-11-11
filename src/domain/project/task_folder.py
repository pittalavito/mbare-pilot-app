"""The agent task as a file inside the repository Copilot works on:
``<repository>/mbare-pilot/<task note>/task.md`` (e.g.
``mbare-pilot/agent-task-login/task.md``). It is **minimal** (``minimal_task``):
title, type, the task's name and where the rest is. The task itself and its
references Copilot reads through the app's MCP server (controller/mcp_server.py),
when it needs them; nothing else is copied into the repository.

The folder is rebuilt before every turn and stays after the session.
Only that one folder is ever deleted, never the rest of ``mbare-pilot/``. It is
visible to git: ignoring or committing it is the user's call (the app leaves
it out of its own lists of changed files, see ``is_task_path``)."""
import shutil
from pathlib import Path, PurePosixPath

from core.error import ValidationError
from domain.project.data_paths import FILE_LINK_PREFIX, NOTE_SUFFIX, REPO_TASKS_DIR, TASK_FILE, note_file_name

_FILES_SUBFOLDER = FILE_LINK_PREFIX.rstrip("/")


def relative_folder(task_note: str) -> str:
    """``mbare-pilot/agent-task-login``: the folder of a task, relative to the
    repository (POSIX separators, as the prompt shows it)."""
    return f"{REPO_TASKS_DIR}/{note_file_name(task_note).removesuffix(NOTE_SUFFIX)}"


def write(repository: Path, task_note: str, files: dict[str, bytes]) -> Path:
    """The task's folder in ``repository`` with exactly ``files`` (name →
    content; ``files/<name>`` goes in its ``files/`` subfolder, any other
    folder part is dropped), rebuilt from scratch. ValidationError when ``mbare-pilot`` or the
    task's folder is not a plain folder (a file, or a link, which could lead
    out of the repository: the app never deletes or writes through one)."""
    root = repository.resolve()
    base = root / REPO_TASKS_DIR
    target = root / relative_folder(task_note)
    for path in (base, target):
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise ValidationError(f"{path} deve essere una cartella: lì l'app scrive il task per Copilot.")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for name, content in files.items():
        parts = PurePosixPath(name.replace("\\", "/"))
        folder = target / _FILES_SUBFOLDER if parts.parent.name == _FILES_SUBFOLDER else target  # files/<name>: the uploaded files
        folder.mkdir(exist_ok=True)
        (folder / parts.name).write_bytes(content)
    return target


def remove(repository: Path, task_note: str) -> bool:
    """The task's folder out of ``repository`` (the «Verifica sviluppo»
    cleanup), and ``mbare-pilot/`` too when nothing else is left in it.
    False when there was none; ValidationError for a link or a file there."""
    root = repository.resolve()
    base = root / REPO_TASKS_DIR
    target = root / relative_folder(task_note)
    for path in (base, target):
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise ValidationError(f"{path} non è una cartella: non la tocco.")
    if not target.exists():
        return False
    shutil.rmtree(target)
    if not any(base.iterdir()):
        base.rmdir()
    return True


def minimal_task(task_note: str, title: str, kind: str) -> dict[str, bytes]:
    """The task's folder content: ``task.md`` with the title, the type (its
    label), the task's name and how to read the rest (MCP)."""
    text = (
        f"# {' '.join(title.split())}\n\nTipo: {kind} · Task: {note_file_name(task_note)}\n\n"
        "Qui c'è solo il titolo. Il task completo (obiettivo, contesto, criteri di accettazione, vincoli, checklist) e i "
        "riferimenti collegati li leggi con i tool MCP del server «mbare-pilot»: read_task, list_references, read_reference.\n"
        "Durante l'esecuzione, se ti serve una mia decisione, chiedimela con ask_user; quando hai finito chiama finish "
        "con un riassunto di cosa hai fatto.\n"
    )
    return {TASK_FILE: text.encode("utf-8")}


def is_task_path(path: str) -> bool:
    """A path of ``git status`` (relative, POSIX) inside ``mbare-pilot/``: the
    app's own files for Copilot, not a change to the code."""
    return REPO_TASKS_DIR in PurePosixPath(path).parts
