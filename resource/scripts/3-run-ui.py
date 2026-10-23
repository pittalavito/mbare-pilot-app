"""Frontend: the Streamlit UI (ui/main.py) on UI_PORT. It needs the API running
(3-run-api.py) at API_URL."""
import subprocess
import sys

from utils import env_value, get_project_root, load_env, uv_command


def run_ui() -> int:
    load_env()
    port = env_value("UI_PORT", "8502")
    result = subprocess.run(
        uv_command() + ["run", "streamlit", "run", "ui/main.py", "--server.port", port],
        cwd=get_project_root(),
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(run_ui())
