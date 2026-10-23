"""Model for the local files store: callers only ever see the ``file_id``,
the actual path stays an implementation detail of the store."""
from pydantic import BaseModel


class StoredFile(BaseModel):
    """A file under the file store root."""
    file_id: str
    size: int
    mtime_ns: int
