import shutil
import subprocess
import sys

from utils import get_project_root


def start_venv() -> int:
    project_root = get_project_root()

    uv = shutil.which("uv")
    if not uv:
        print("Error: uv not found. Install it from https://docs.astral.sh/uv/getting-started/installation/")
        return 1

    # uv sync creates .venv when missing and installs the dev group by default
    sync = subprocess.run([uv, "sync"], cwd=project_root)
    return sync.returncode


if __name__ == "__main__":
    sys.exit(start_venv())
