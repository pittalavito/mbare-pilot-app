import subprocess
import sys

from utils import get_project_root, uv_command


def run_test() -> int:
    project_root = get_project_root()
    coverage_target = str(project_root / "src")
    uv = uv_command()

    sync = subprocess.run(uv + ["sync"], cwd=project_root)
    if sync.returncode != 0:
        return sync.returncode

    result = subprocess.run(
        uv + ["run", "pytest", "-v", f"--cov={coverage_target}", "--cov-report=term-missing"],
        cwd=project_root,
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(run_test())
