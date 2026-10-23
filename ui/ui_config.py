"""UI settings, read from the same .env as the backend. The UI only needs to
know where the API is and how to start the backend processes: it never
touches the DB, files or services directly."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# ui/ui_config.py -> parents[1] is the project root.
_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class UiConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    api_url: str = "http://127.0.0.1:8000"
    """Base URL of the backend API."""
    api_reload: bool = False
    """The API started from the Backend panel restarts by itself when its source changes (development)."""

    # --- Backend processes started from the Backend panel (paths from the project root) ---
    api_app: str = "api:app"
    """ASGI app of the API, as uvicorn wants it (``module:attribute``)."""
    api_app_dir: str = "src"
    """Folder of the API module; also the one watched by the reload."""
    worker_script: str = "src/worker.py"

    # --- Scripts mentioned in the UI ---
    script_start_docker: str = "resource/scripts/start-docker.py"
