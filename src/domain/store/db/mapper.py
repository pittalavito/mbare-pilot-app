"""What the per-aggregate mappers (``*_mapper.py``) share."""
from datetime import datetime, timezone


def as_utc(value: datetime) -> datetime:
    """Backends without timezone support (e.g. SQLite) return naive datetimes: they are UTC."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
