from pathlib import Path

import config as config_module
from config import Config


def _config(**overrides) -> Config:
    values = dict(
        database_url="postgresql+psycopg://app:supersecret@localhost:5433/app",
        redis_url="redis://localhost:6380/0",
        openai_api_key="sk-real-key",
    )
    values.update(overrides)
    return Config(_env_file=None, **values)


def test_masked_hides_secrets_and_url_passwords():
    masked = _config().masked()

    assert masked["openai_api_key"] == "********"
    assert masked["database_url"] == "postgresql+psycopg://app:********@localhost:5433/app"
    assert "supersecret" not in str(masked) and "sk-real-key" not in str(masked)


def test_masked_keeps_empty_secrets_empty_and_plain_values():
    masked = _config(openai_api_key="").masked()

    assert masked["openai_api_key"] == ""
    assert masked["redis_url"] == "redis://localhost:6380/0"
    assert masked["postgres_dashboard_port"] == 8084
    assert masked["redis_dashboard_port"] == 8083


def test_backup_folder_defaults_next_to_the_project(config, tmp_path):
    project_root = Path(config_module.__file__).resolve().parents[1]  # src/config.py → the project folder
    assert config.backup_path == project_root.parent / "mbare-pilot-back-up"
    assert config.model_copy(update={"backup_dir": str(tmp_path)}).backup_path == tmp_path


def test_the_automation_cache_settings_still_accept_their_old_names(monkeypatch):
    monkeypatch.setenv("CHAT_ROUTE_THRESHOLD", "0.7")
    monkeypatch.setenv("AUTOMATION_CACHE_EMBEDDER", "openrouter/x")
    config = Config(_env_file=None, database_url="sqlite://", redis_url="redis://x", mbare_pilot_secret_key="k")

    assert (config.automation_cache_threshold, config.automation_cache_embedder) == (0.7, "openrouter/x")
