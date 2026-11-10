"""Evaluate «Elabora WIP» on resource/eval/wip with one or more catalog models,
the same as the button in Admin → Observability → Metriche. Postgres must be
running (start-docker.py); the API is not needed. The report goes in
<MBARE_PILOT_HOME>/evaluations/.

    python resource/scripts/eval-wip.py --model openrouter/google/gemini-3.1-flash-lite-preview [--model ...]
"""
import os
import subprocess
import sys

from utils import get_project_root, uv_command


def evaluate(arguments: list[str]) -> int:
    project_root = get_project_root()
    env = {**os.environ, "PYTHONPATH": str(project_root / "src")}
    command = uv_command() + ["run", "python", str(project_root / "src" / "evaluation_cli.py"), "wip", *arguments]
    return subprocess.run(command, cwd=project_root, env=env).returncode


if __name__ == "__main__":
    sys.exit(evaluate(sys.argv[1:]))
