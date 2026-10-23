from domain.store.redis.repository import AGENT_TRACE_KEYSPACE
from domain.store.redis.store import Factory, RedisTraceRepository
from fakes import make_run_record


def test_save_and_load(redis_client):
    repository = RedisTraceRepository(redis_client)
    repository.save(Factory.to_trace_record(make_run_record("run-1")))

    trace = repository.load("run-1")
    assert trace is not None
    assert trace.tool_calls[0].name == "hello_world"


def test_load_missing_returns_none(redis_client):
    assert RedisTraceRepository(redis_client).load("missing") is None


def test_malformed_value_returns_none(redis_client):
    redis_client.set(AGENT_TRACE_KEYSPACE.key("bad"), "not json")
    assert RedisTraceRepository(redis_client).load("bad") is None
