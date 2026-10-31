from datetime import datetime, timedelta, timezone

from domain.store.db.run_mapper import Factory
from domain.store.db.run_repository import DbRunRepository
from fakes import make_run_record


def _save(repository: DbRunRepository, run_id: str, created_at: datetime | None = None) -> None:
    record = make_run_record(run_id, created_at=created_at)
    repository.save_rows(Factory.to_run_row(record), Factory.to_tool_rows(record))


def test_save_and_get(engine):
    repository = DbRunRepository(engine)
    _save(repository, "run-1")

    row = repository.get("run-1")
    assert row is not None
    assert row.tool_names == "hello_world"
    assert row.total_input_tokens == 150


def test_list_recent_most_recent_first(engine):
    repository = DbRunRepository(engine)
    now = datetime.now(timezone.utc)
    _save(repository, "old", created_at=now - timedelta(hours=1))
    _save(repository, "new", created_at=now)

    assert [row.run_id for row in repository.list_recent()] == ["new", "old"]
    assert [row.run_id for row in repository.list_recent_tool_calls()] == ["new", "old"]


def test_delete(engine):
    repository = DbRunRepository(engine)
    _save(repository, "run-1")

    assert repository.delete("run-1") is True
    assert repository.delete("run-1") is False
