"""The backend processes the UI can start and stop, built from the UI config
(API host and port come from API_URL, so the UI starts the API exactly where
it will look for it)."""
import sys
from pathlib import Path
from urllib.parse import urlparse

from process_control.manager import ManagedService, ProcessManager

# ui/process_control/services.py -> parents[2] is the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def backend_services(api_url: str) -> list[ManagedService]:
    url = urlparse(api_url)
    host, port = url.hostname or "127.0.0.1", str(url.port or 8000)
    python = sys.executable  # the project's venv: the UI runs in it too
    return [
        ManagedService(
            name="api", label="API",
            command=[python, "-m", "uvicorn", "api:app", "--app-dir", "src", "--host", host, "--port", port],
            health_url=f"{api_url.rstrip('/')}/health",
        ),
        ManagedService(name="worker", label="Worker automation", command=[python, "src/worker.py"]),
    ]


def process_manager() -> ProcessManager:
    return ProcessManager(
        cwd=PROJECT_ROOT,
        run_dir=PROJECT_ROOT / "resource" / "run",
        log_dir=PROJECT_ROOT / "resource" / "logs",
    )
