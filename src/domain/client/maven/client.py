"""Maven run as a subprocess in a repository's folder, for the one goal the
app needs: ``jacoco:report``, which turns the ``target/jacoco.exec`` the
tests left into ``target/site/jacoco/jacoco.xml``. It does not run the tests
and it changes nothing outside ``target/``.

The repository's wrapper (``mvnw``, ``mvnw.cmd`` on Windows) wins over the
``mvn`` on PATH, so the build uses the Maven version the project pins."""
import os
import shutil
import subprocess
from pathlib import Path

from core.error import UpstreamError

_TIMEOUT_SECONDS = 180
_OUTPUT_TAIL_LINES = 8
"""Maven prints its errors on stdout: the last lines are kept for the message."""


class MavenClient:

    def __init__(self, executable: str | None = None, timeout: int = _TIMEOUT_SECONDS):
        """``executable`` defaults to the repository's wrapper, then ``mvn`` on PATH."""
        self._executable = executable
        self._timeout = timeout

    def jacoco_report(self, cwd: Path) -> None:
        """``mvn -q -B jacoco:report`` in ``cwd`` (the reactor: every module
        with a ``jacoco.exec`` gets its XML). UpstreamError when Maven is
        missing, too slow or fails."""
        self._run(cwd, ["jacoco:report"])

    def _command(self, cwd: Path) -> str:
        if self._executable:
            return self._executable
        wrapper = cwd / ("mvnw.cmd" if os.name == "nt" else "mvnw")
        if wrapper.is_file():
            return str(wrapper)
        found = shutil.which("mvn")
        if not found:
            raise UpstreamError("mvn non trovato: installa Maven e mettilo nel PATH (o aggiungi mvnw al repository).")
        return found

    def _run(self, cwd: Path, goals: list[str]) -> None:
        command = [self._command(cwd), "-q", "-B", *goals]
        try:
            result = subprocess.run(
                command, cwd=cwd, capture_output=True, encoding="utf-8", errors="replace",
                timeout=self._timeout, stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired as exc:
            raise UpstreamError(f"mvn {' '.join(goals)} non ha risposto entro {self._timeout}s ({cwd}).") from exc
        except OSError as exc:
            raise UpstreamError(f"Impossibile eseguire mvn: {exc}") from exc
        if result.returncode != 0:
            output = (result.stdout + "\n" + result.stderr).strip().splitlines()
            tail = " | ".join(line.strip() for line in output[-_OUTPUT_TAIL_LINES:] if line.strip())
            raise UpstreamError(f"mvn {' '.join(goals)} fallito ({cwd}): {tail or result.returncode}")
