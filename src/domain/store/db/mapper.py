"""What the per-aggregate mappers (``*_mapper.py``) share."""
from datetime import datetime, timezone
from typing import Protocol


def as_utc(value: datetime) -> datetime:
    """Backends without timezone support (e.g. SQLite) return naive datetimes: they are UTC."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class _Row(Protocol):
    id: int | None


def saved_id(row: _Row) -> int:
    """The id of a row read from the DB or just saved. Tables declare ``id``
    as ``int | None`` because a new row has none until it is inserted."""
    if row.id is None:
        raise ValueError(f"{type(row).__name__} senza id: non è ancora stata salvata")
    return row.id
