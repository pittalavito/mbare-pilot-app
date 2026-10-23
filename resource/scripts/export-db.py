"""Export the Postgres DB as SQL into <BACKUP_DIR>/db/ (default: the
mbare-pilot-back-up folder next to the project), the same as Admin → Backup.
Postgres must be running (start-docker.py); the API is not needed.

    python resource/scripts/export-db.py
"""
import os
import subprocess
import sys

from utils import get_project_root, uv_command

_EXPORT = (
    "from service.backup_service import BackupService\n"
    "backup = BackupService.from_config().export_db()\n"
    "print(f'DB esportato: {backup.name} ({backup.size / 1024:.0f} KB)')\n"
)


def export_db() -> int:
    project_root = get_project_root()
    env = {**os.environ, "PYTHONPATH": str(project_root / "src")}
    result = subprocess.run(uv_command() + ["run", "python", "-c", _EXPORT], cwd=project_root, env=env)
    return result.returncode


if __name__ == "__main__":
    sys.exit(export_db())
