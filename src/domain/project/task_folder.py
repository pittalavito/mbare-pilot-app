"""The agent task and its references as files inside the repository Copilot
works on: ``<repository>/mbare-pilot/<task note>/`` (e.g.
``mbare-pilot/agent-task-login/task.md``). Copilot reads them as any other
file of the repository; the prompt only says where they are.

The folder is rebuilt before every turn (the task and its references may have
changed) and stays after the session: the user can look at what Copilot read.
Only that one folder is ever deleted, never the rest of ``mbare-pilot/``. It is
visible to git: ignoring or committing it is the user's call (the app leaves
it out of its own lists of changed files, see ``is_task_path``)."""
import shutil
from pathlib import Path, PurePosixPath

from core.error import ValidationError
from domain.project.data_paths import NOTE_SUFFIX, REPO_TASKS_DIR, note_file_name


def relative_folder(task_note: str) -> str:
    """``mbare-pilot/agent-task-login``: the folder of a task, relative to the
    repository (POSIX separators, as the prompt shows it)."""
    return f"{REPO_TASKS_DIR}/{note_file_name(task_note).removesuffix(NOTE_SUFFIX)}"


def write(repository: Path, task_note: str, files: dict[str, bytes]) -> Path:
    """The task's folder in ``repository`` with exactly ``files`` (name →
    content), rebuilt from scratch. ValidationError when ``mbare-pilot`` or the
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
        (target / Path(name).name).write_bytes(content)
    return target


def is_task_path(path: str) -> bool:
    """A path of ``git status`` (relative, POSIX) inside ``mbare-pilot/``: the
    app's own files for Copilot, not a change to the code."""
    return REPO_TASKS_DIR in PurePosixPath(path).parts
