"""Evaluate the context search (RAG) on resource/eval/rag with one or more embedders,
the same as the button in Admin → Observability → Metriche. Postgres must be
running (start-docker.py); the API is not needed. The report goes in
<MBARE_PILOT_HOME>/evaluations/.

    python resource/scripts/eval-rag.py [--embedder hashing] [--embedder openrouter/openai/text-embedding-3-small]
"""
import os
import subprocess
import sys

from utils import get_project_root, uv_command


def evaluate(arguments: list[str]) -> int:
    project_root = get_project_root()
    env = {**os.environ, "PYTHONPATH": str(project_root / "src")}
    command = uv_command() + ["run", "python", str(project_root / "src" / "evaluation_cli.py"), "rag", *arguments]
    return subprocess.run(command, cwd=project_root, env=env).returncode


if __name__ == "__main__":
    sys.exit(evaluate(sys.argv[1:]))
