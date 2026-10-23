"""Backups of the app's data: exports of the Postgres DB, kept as files in the
backup folder (BACKUP_DIR)."""
from datetime import datetime

from pydantic import BaseModel


class BackupFile(BaseModel):
    name: str
    """File name inside the backup folder, e.g. ``mbare-pilot-db-20261023-205500.sql``."""
    size: int
    """Bytes."""
    created_at: datetime
