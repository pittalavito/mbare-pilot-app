"""Application configuration, loaded from environment variables / .env.
One app-wide instance: read it anywhere with ``Config.get()``, never pass it
around. Tests replace it with ``Config.set(...)``."""
import re
from pathlib import Path
from typing import ClassVar

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SENSITIVE_KEY_MARKERS = ("password", "api_key", "secret", "token")
_MASK = "********"
_URL_CREDENTIALS = re.compile(r"://([^:/@]+):([^@]+)@")


class Config(BaseSettings):
    
    # The name model_config is required by pydantic-settings: renamed, .env is not read.
    model_config = SettingsConfigDict(env_file=_PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore")
    _instance: ClassVar["Config | None"] = None
    
    # --- App ---
    app_log_level: str = "INFO"

    # --- Postgres ---
    database_url: str
    postgres_container: str = "mbare-pilot-app-postgres"
    """Docker container of Postgres (resource/docker/docker-compose.yml): the DB export runs pg_dump in it."""
    postgres_dashboard_port: int = 8084
    """Adminer (resource/docker/docker-compose.yml)."""

    # --- Redis ---
    redis_url: str
    redis_dashboard_port: int = 8083
    """Redis Commander (resource/docker/docker-compose.yml)."""

    # --- App data ---
    mbare_pilot_home: str = ""
    """The app's data folder, apart from the projects' code: ``definition/``
    (agents, chatbots, automations as YAML) and ``files/`` (each project's notes,
    uploaded files and context). Empty = ``~/.mbare-pilot``."""

    # --- Backups ---
    backup_dir: str = ""
    """Where DB exports are written (``<backup_dir>/db/``). Empty = the
    ``mbare-pilot-back-up`` folder next to the project."""

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

    # --- Automation cache (automation chatbots) ---
    automation_cache_threshold: float = Field(0.9, validation_alias=AliasChoices("automation_cache_threshold", "chat_route_threshold"))
    """How similar (cosine, 0..1) a message must be to a cached one to launch
    its automation without the agent. CHAT_ROUTE_THRESHOLD, its old name, still works."""
    automation_cache_embedder: str = Field("hashing", validation_alias=AliasChoices("automation_cache_embedder", "chat_route_embedder"))
    """Embedder of the cache: ``hashing`` (a mock: same words = similar) or
    ``openrouter/<model>`` (e.g. ``openrouter/openai/text-embedding-3-small``;
    the text is masked before it leaves the PC). CHAT_ROUTE_EMBEDDER, its old name, still works."""

    # --- Worker (started and stopped by the API) ---
    worker_script: str = "src/worker.py"
    """The worker's entry point, relative to the app folder."""

    # --- GitHub Copilot CLI (agent tasks delegated from the app) ---
    copilot_command: str = "copilot"
    """The CLI: a name on the PATH or a path (npm install -g @github/copilot)."""
    copilot_model: str = ""
    """Empty = Copilot's default model."""
    copilot_github_token: SecretStr | None = None
    """A GitHub token for Copilot; empty = the login made with ``copilot`` → /login."""
    copilot_planning_timeout_minutes: float = 5
    """A turn of the planning chat (the API waits for it)."""
    copilot_execution_timeout_minutes: float = 60
    """An execution in the worker."""

    # --- Datapizza tracing ---
    datapizza_trace_summary: bool = False
    """Print datapizza's "Trace Summary" panel (spans, duration, tokens) to the console after every run."""

    @classmethod
    def get(cls) -> "Config":
        """The app-wide Config, loaded from .env on first access."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def set(cls, config: "Config | None") -> None:
        """Replace the app-wide Config (tests). None reloads it from .env on the next ``get()``."""
        cls._instance = config

    @property
    def secret_key(self) -> str | None:
        """The plain MBARE_PILOT_SECRET_KEY, None when unset."""
        return self.mbare_pilot_secret_key.get_secret_value() if self.mbare_pilot_secret_key else None

    @property
    def app_root(self) -> Path:
        """The app's folder (the one with src/, web/ and the .env)."""
        return _PROJECT_ROOT

    @property
    def web_dist(self) -> Path:
        """The built frontend (``npm run build`` in web/), served by the API at ``/``."""
        return _PROJECT_ROOT / "web" / "dist"

    @property
    def run_dir(self) -> Path:
        """PID files of the background processes (``resource/run``)."""
        return _PROJECT_ROOT / "resource" / "run"

    @property
    def logs_dir(self) -> Path:
        """Logs of the API and the worker (``resource/logs/<name>.log``)."""
        return _PROJECT_ROOT / "resource" / "logs"

    @property
    def project_data_root(self) -> Path:
        """Root of the projects' data: ``<data_home>/project/<slug>/{notes,files,context}``."""
        return self.data_home / "project"

    @property
    def definitions_root(self) -> Path:
        """Root of the definitions as files: ``<data_home>/definition`` (global ones, ``project/<slug>/``)."""
        return self.data_home / "definition"

    @property
    def backup_path(self) -> Path:
        return Path(self.backup_dir).expanduser() if self.backup_dir else _PROJECT_ROOT.parent / "mbare-pilot-back-up"

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

