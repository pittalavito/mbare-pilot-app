"""A command run as a subprocess in a repository's folder (the tests of the
«Verifica sviluppo»): no shell, stdin closed, output (stdout and stderr
together) and exit code returned; only a command that cannot start or does
not finish in time is an error."""
import subprocess
from dataclasses import dataclass
from pathlib import Path

from core.error import UpstreamError


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    output: str


class CommandClient:

    def run(self, cwd: Path, arguments: list[str], timeout_seconds: int) -> CommandResult:
        try:
            result = subprocess.run(
                arguments, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8", errors="replace",
                timeout=timeout_seconds, stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired as exc:
            raise UpstreamError(f"{' '.join(arguments)} non è finito entro {timeout_seconds // 60} minuti.") from exc
        except OSError as exc:
            raise UpstreamError(f"Impossibile eseguire {arguments[0]}: {exc}") from exc
        return CommandResult(returncode=result.returncode, output=result.stdout or "")
