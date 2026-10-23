import shutil
import subprocess
import sys

from utils import get_project_root

COMPOSE_FILE = "resource/docker/docker-compose.yml"
ENV_FILE = ".env"


def start_docker() -> int:
    project_root = get_project_root()

    docker = shutil.which("docker")
    if not docker:
        print("Error: docker not found. Install Docker Desktop / docker engine.")
        return 1

    if not (project_root / ENV_FILE).is_file():
        print(f"Error: {ENV_FILE} not found — copy it from .env.example first.")
        return 1

    result = subprocess.run(
        [docker, "compose", "--env-file", ENV_FILE, "-f", COMPOSE_FILE, "up", "-d"],
        cwd=project_root,
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(start_docker())
