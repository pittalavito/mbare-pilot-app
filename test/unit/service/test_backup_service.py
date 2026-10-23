"""BackupService with a fake pg_dump: files written in the backup folder,
listed newest first, read back; names that could leave the folder rejected."""
import pytest

from core.error import NotFoundError, UpstreamError, ValidationError
from service.backup_service import BackupService


class _FakeDump:

    def __init__(self, error: Exception | None = None):
        self.calls = []
        self.error = error

    def dump(self, user, database):
        self.calls.append((user, database))
        if self.error:
            raise self.error
        return b"-- dump\nCREATE TABLE project ();\n"


@pytest.fixture
def dump():
    return _FakeDump()


@pytest.fixture
def service(tmp_path, dump):
    return BackupService(tmp_path / "back-up", "postgresql+psycopg://app:secret@localhost:5433/appdb", dump)


def test_export_writes_a_sql_file_in_the_db_folder(service, dump, tmp_path):
    backup = service.export_db()

    assert dump.calls == [("app", "appdb")]
    assert backup.name.startswith("mbare-pilot-db-") and backup.name.endswith(".sql")
    assert (tmp_path / "back-up" / "db" / backup.name).read_bytes().startswith(b"-- dump")
    assert service.read_backup(backup.name) == b"-- dump\nCREATE TABLE project ();\n"


def test_list_is_newest_first_and_ignores_other_files(service, tmp_path):
    folder = tmp_path / "back-up" / "db"
    folder.mkdir(parents=True)
    for name in ("mbare-pilot-db-20261001-100000.sql", "mbare-pilot-db-20261002-100000.sql", "note.txt"):
        (folder / name).write_text("x", encoding="utf-8")

    assert [b.name for b in service.list_backups()] == [
        "mbare-pilot-db-20261002-100000.sql", "mbare-pilot-db-20261001-100000.sql",
    ]


def test_empty_folder(service):
    assert service.list_backups() == []


@pytest.mark.parametrize("name", ["../secret.sql", "note.txt", "mbare-pilot-db-x.sql"])
def test_invalid_names_rejected(service, name):
    with pytest.raises(ValidationError):
        service.read_backup(name)


def test_missing_backup(service):
    with pytest.raises(NotFoundError):
        service.read_backup("mbare-pilot-db-20261001-100000.sql")


def test_failed_dump_writes_nothing(tmp_path):
    service = BackupService(tmp_path, "postgresql://app@localhost/app", _FakeDump(UpstreamError("container giù")))

    with pytest.raises(UpstreamError):
        service.export_db()
    assert service.list_backups() == []
