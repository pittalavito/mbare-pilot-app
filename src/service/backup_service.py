"""Backups: export the Postgres DB as a SQL file into the backup folder
(``<BACKUP_DIR>/db/``), list the exports, read one back for download.

Used by the API (Admin → Backup) and by resource/scripts/export-db.py, so it
needs no Container: only the Config (DATABASE_URL, BACKUP_DIR, POSTGRES_CONTAINER)."""
import re
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.engine import make_url

from config import Config
from core.error import NotFoundError, ValidationError
from core.observability import LogPrefix, observed
from domain.client.postgres.pg_dump import PgDumpClient
from models.domain.backup import BackupFile

DB_DIR = "db"
_PREFIX = "mbare-pilot-db-"
_NAME = re.compile(rf"^{_PREFIX}\d{{8}}-\d{{6}}\.sql$")


class BackupService:

    def __init__(self, backup_dir: Path, database_url: str, dump_client: PgDumpClient):
        self._dir = backup_dir / DB_DIR
        url = make_url(database_url)
        self._user = url.username or ""
        self._database = url.database or ""
        self._dump = dump_client

    @classmethod
    def from_config(cls) -> "BackupService":
        config = Config.get()
        return cls(config.backup_path, config.database_url, PgDumpClient(config.postgres_container))

    @observed(LogPrefix.BACKUP_SERVICE)
    def export_db(self) -> BackupFile:
        """Dump the whole DB into a new file ``mbare-pilot-db-<date>-<time>.sql``."""
        data = self._dump.dump(self._user, self._database)
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{_PREFIX}{datetime.now():%Y%m%d-%H%M%S}.sql"
        path.write_bytes(data)
        return _to_backup(path)

    def list_backups(self) -> list[BackupFile]:
        """The DB exports, newest first."""
        if not self._dir.is_dir():
            return []
        files = [path for path in self._dir.iterdir() if path.is_file() and _NAME.match(path.name)]
        return [_to_backup(path) for path in sorted(files, key=lambda path: path.name, reverse=True)]

    def read_backup(self, name: str) -> bytes:
        if not _NAME.match(name):
            raise ValidationError(f"Nome di backup non valido: {name!r}")
        path = self._dir / name
        if not path.is_file():
            raise NotFoundError(f"Backup non trovato: {name}")
        return path.read_bytes()


def _to_backup(path: Path) -> BackupFile:
    stat = path.stat()
    return BackupFile(name=path.name, size=stat.st_size, created_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc))
