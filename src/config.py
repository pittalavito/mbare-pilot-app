"""Application configuration, loaded from environment variables / .env.
One app-wide instance: read it anywhere with ``Config.get()``, never pass it
around. Tests replace it with ``Config.set(...)``."""
import re
from pathlib import Path
from typing import ClassVar

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# src/config.py -> parents[1] is the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]

_SENSITIVE_KEY_MARKERS = ("password", "api_key", "secret", "token")
_MASK = "********"
_URL_CREDENTIALS = re.compile(r"://([^:/@]+):([^@]+)@")


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    _instance: ClassVar["Config | None"] = None

    @classmethod
    def get(cls) -> "Config":
        """The app-wide Config, loaded from .env on first access."""
        if cls._instance is None:
            cls._instance = cls()  # pyright: ignore[reportCallIssue]
        return cls._instance

    @classmethod
    def set(cls, config: "Config | None") -> None:
        """Replace the app-wide Config (tests). None reloads it from .env on the next ``get()``."""
        cls._instance = config

    # --- App ---
    app_log_level: str = "INFO"

    # --- API (FastAPI backend, called by the UI in ui/) ---
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    # --- Postgres ---
    database_url: str
    postgres_dashboard_port: int = 8084
    """Adminer (resource/docker/docker-compose.yml)."""

    # --- Redis ---
    redis_url: str
    redis_dashboard_port: int = 8083
    """Redis Commander (resource/docker/docker-compose.yml)."""

    # --- App data ---
    mbare_pilot_home: str = ""
    """Where the app keeps the projects' data (notes, uploaded files), apart from
    their code folders. Empty = ``~/.mbare-pilot``."""

    # --- Projects ---
    project_roots: str = ""
    """Folders the project picker may browse, separated by ``;``. Empty = the
    user's home folder. Projects can only live inside these roots."""

    # --- Secrets ---
    mbare_pilot_secret_key: SecretStr | None = None
    """Fernet key encrypting the secrets saved in the DB (core/secret_box.py)."""

    # --- LLM providers ---
    openrouter_api_key: SecretStr | None = None
    """Main provider: https://openrouter.ai/settings/keys"""
    openrouter_url: str = "https://openrouter.ai/api/v1"
    openai_api_key: SecretStr | None = None
    ollama_url: str = "http://localhost:11434/v1"

    # --- Datapizza tracing ---
    datapizza_trace_summary: bool = False
    """Print datapizza's "Trace Summary" panel (spans, duration, tokens) to the console after every run."""

    @property
    def secret_key(self) -> str | None:
        """The plain MBARE_PILOT_SECRET_KEY, None when unset."""
        return self.mbare_pilot_secret_key.get_secret_value() if self.mbare_pilot_secret_key else None

    @property
    def projects_data_root(self) -> Path:
        """Root of the projects' data folders (``<data_home>/projects``)."""
        return self.data_home / "projects"

    @property
    def data_home(self) -> Path:
        return Path(self.mbare_pilot_home).expanduser() if self.mbare_pilot_home else Path.home() / ".mbare-pilot"

    @property
    def project_root_paths(self) -> list[Path]:
        roots = [Path(part.strip()) for part in self.project_roots.split(";") if part.strip()]
        return roots or [Path.home()]

    def masked(self) -> dict[str, object]:
        """Every setting with secrets masked, safe to show in the UI: secret and
        key/password/token fields become asterisks (empty ones stay empty) and
        credentials embedded in URLs (e.g. DATABASE_URL) are scrubbed."""
        result: dict[str, object] = {}
        for name, value in self.model_dump().items():
            if isinstance(value, SecretStr):
                value = value.get_secret_value()
            if value in (None, ""):
                result[name] = value
            elif any(marker in name for marker in _SENSITIVE_KEY_MARKERS):
                result[name] = _MASK
            elif isinstance(value, str):
                result[name] = _URL_CREDENTIALS.sub(rf"://\1:{_MASK}@", value)
            else:
                result[name] = value
        return result

