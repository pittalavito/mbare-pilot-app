"""``pg_dump`` of the app's Postgres, run inside its Docker container (the
image ships the matching pg_dump, nothing to install on the PC). The dump is
plain SQL: tables, data and the pgvector extension, restorable with ``psql``."""
import shutil
import subprocess

from core.error import UpstreamError

_TIMEOUT_SECONDS = 300


class PgDumpClient:

    def __init__(self, container: str, executable: str | None = None):
        """``container``: the Postgres container (POSTGRES_CONTAINER); ``executable``
        defaults to ``docker`` on PATH."""
        self._container = container
        self._executable = executable or shutil.which("docker")

    def dump(self, user: str, database: str) -> bytes:
        """The whole database as SQL. ``--clean --if-exists`` drops each object
        before recreating it, so the dump restores over an existing DB."""
        if not self._executable:
            raise UpstreamError("docker non trovato: serve per esportare il DB dal container Postgres.")
        command = [
            self._executable, "exec", self._container,
            "pg_dump", "--username", user, "--dbname", database, "--clean", "--if-exists", "--no-owner",
        ]
        try:
            result = subprocess.run(command, capture_output=True, timeout=_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as exc:
            raise UpstreamError(f"pg_dump non ha finito entro {_TIMEOUT_SECONDS}s.") from exc
        except OSError as exc:
            raise UpstreamError(f"Impossibile eseguire docker: {exc}") from exc
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip() or result.returncode
            raise UpstreamError(f"Export del DB fallito (container {self._container}): {detail}")
        return result.stdout
