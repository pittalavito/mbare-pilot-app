"""The backend processes the UI can start and stop, built from the UI config
(API host and port come from API_URL, so the UI starts the API exactly where
it will look for it; entry points and paths from the .env too)."""
import sys
from pathlib import Path
from urllib.parse import urlparse

from process_control.manager import ManagedService, ProcessManager
from ui_config import UiConfig

# ui/process_control/services.py -> parents[2] is the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def backend_services(config: UiConfig) -> list[ManagedService]:
    """API and worker, as configured in the .env (API_URL, API_RELOAD, API_APP,
    API_APP_DIR, WORKER_SCRIPT)."""
    url = urlparse(config.api_url)
    host, port = url.hostname or "127.0.0.1", str(url.port or 8000)
    python = sys.executable  # the project's venv: the UI runs in it too
    api_command = [
        python, "-m", "uvicorn", config.api_app, "--app-dir", config.api_app_dir, "--host", host, "--port", port,
    ]
    if config.api_reload:
        api_command += ["--reload", "--reload-dir", config.api_app_dir]
    return [
        ManagedService(
            name="api", label="API" + (" (reload)" if config.api_reload else ""),
            command=api_command,
            health_url=f"{config.api_url.rstrip('/')}/health",
        ),
        ManagedService(
            name="worker", label="Worker automation", command=[python, config.worker_script],
            health_url=f"{config.api_url.rstrip('/')}/workers/health",  # its heartbeat, through the API
        ),
    ]


def process_manager() -> ProcessManager:
    return ProcessManager(
        cwd=PROJECT_ROOT,
        run_dir=PROJECT_ROOT / "resource" / "run",
        log_dir=PROJECT_ROOT / "resource" / "logs",
    )
