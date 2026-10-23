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
