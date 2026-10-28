"""The example definitions shipped with the app (resource/definition-example/):
a starting point for ``<MBARE_PILOT_HOME>/definition/``, copied by
resource/scripts/init-definitions.py. Only missing files are copied: the
user's own are never overwritten."""
import shutil
from pathlib import Path

EXAMPLES_DIR = Path(__file__).resolve().parents[3] / "resource" / "definition-example"
"""In the repository, next to the code."""

_SKIP = {"README.md"}
"""About the examples, not a definition."""


def copy_missing(target: Path, source: Path = EXAMPLES_DIR) -> list[str]:
    """Copy into ``target`` the example files it lacks; returns their paths
    relative to ``target`` (posix), sorted. Existing files are left as they are."""
    copied = []
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if not path.is_file() or relative.as_posix() in _SKIP:
            continue
        destination = target / relative
        if destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        copied.append(relative.as_posix())
    return copied
