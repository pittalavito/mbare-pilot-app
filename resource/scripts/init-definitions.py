"""Copy the example definitions (resource/definition-example/) into
<MBARE_PILOT_HOME>/definition/: only the files that are missing, never
overwriting yours. For a new installation: without global-coding-agent.yml
Copilot does not start. The API is not needed.

    python resource/scripts/init-definitions.py
"""
import os
import subprocess
import sys

from utils import get_project_root, uv_command

_INIT = (
    "from config import Config\n"
    "from domain.project.definition_examples import copy_missing\n"
    "target = Config.get().definitions_root\n"
    "copied = copy_missing(target)\n"
    "print(f'Cartella: {target}')\n"
    "print('\\n'.join(f'  copiato: {name}' for name in copied) or '  niente da copiare: sono tutti presenti')\n"
)


def init_definitions() -> int:
    project_root = get_project_root()
    env = {**os.environ, "PYTHONPATH": str(project_root / "src")}
    result = subprocess.run(uv_command() + ["run", "python", "-c", _INIT], cwd=project_root, env=env)
    return result.returncode


if __name__ == "__main__":
    sys.exit(init_definitions())
