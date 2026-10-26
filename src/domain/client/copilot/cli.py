"""Finding the Copilot CLI to run. npm installs a ``.cmd`` launcher on Windows,
which would cut the prompt at its first newline: node is called with
Copilot's script instead."""
import shutil
import subprocess
import sys
from pathlib import Path

NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
"""No console window for Copilot when the worker runs without one."""


def resolve(command: str) -> list[str] | None:
    """The argv prefix that runs the CLI (a name on the PATH or a path); None
    when not found. On Windows the npm ``.cmd`` launcher becomes
    ``node <npm-loader.js>`` (a .cmd would truncate multi-line arguments)."""
    path = shutil.which(command)
    if path is None:
        return None
    if Path(path).suffix.lower() in {".cmd", ".bat"}:
        loader = Path(path).parent / "node_modules" / "@github" / "copilot" / "npm-loader.js"
        node = Path(path).parent / "node.exe" if (Path(path).parent / "node.exe").exists() else shutil.which("node")
        if loader.is_file() and node:
            return [str(node), str(loader)]
    return [path]
