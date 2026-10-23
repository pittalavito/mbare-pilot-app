"""UI settings, read from the same .env as the backend. The UI only needs to
know where the API is: it never touches the DB, files or services directly."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# ui/ui_config.py -> parents[1] is the project root.
_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class UiConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    api_url: str = "http://127.0.0.1:8000"
    """Base URL of the backend (resource/scripts/3-run-api.py)."""
