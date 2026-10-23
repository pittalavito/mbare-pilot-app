import datapizza.tracing
import fakeredis
import pytest

from config import Config
from core.container import Container
from domain.store.redis.repository import Client


@pytest.mark.parametrize("enabled", [True, False])
def test_trace_summary_setting_controls_datapizza_console(enabled, config, tmp_path, monkeypatch):
    monkeypatch.setattr(Client, "create_redis_client", staticmethod(lambda url: fakeredis.FakeRedis(decode_responses=True)))
    Config.set(config.model_copy(update={"mbare_pilot_home": str(tmp_path), "datapizza_trace_summary": enabled}))

    Container()

    assert datapizza.tracing.console.quiet is (not enabled)


def test_get_loads_once_and_set_replaces(config):
    assert Config.get() is config
    other = config.model_copy(update={"app_log_level": "DEBUG"})

    Config.set(other)

    assert Config.get() is other
