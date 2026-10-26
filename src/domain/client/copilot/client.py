"""GitHub Copilot CLI as a subprocess: one turn (``copilot -p``) per call, in a
session whose id the app chooses (``--session-id``), so Copilot keeps the
conversation across calls.

Two modes:

- **plan**: ``--mode plan``. Copilot reads the code and answers; the CLI
  itself blocks every change outside its session folder.
- **execute**: ``--mode autopilot --allow-all-tools``, minus the tools the
  caller denies (``denied_tools``, from the coding-agent definition).

Finding the CLI is in cli.py, running it in process.py, reading its output
in output.py."""
import os
import subprocess
from collections.abc import Callable, Sequence
from enum import StrEnum
from pathlib import Path

from domain.client.copilot import process
from domain.client.copilot.cli import NO_WINDOW, resolve
from domain.client.copilot.output import to_turn
from models.domain.copilot import CopilotTurn

NOT_FOUND = "Copilot CLI non trovato: installalo (npm install -g @github/copilot) e fai il login."


class CopilotMode(StrEnum):
    PLAN = "plan"
    EXECUTE = "execute"


class CopilotClient:

    def __init__(self, command: str | list[str] = "copilot", model: str = "", token: str | None = None):
        """``command``: the CLI (name on the PATH or path; an argv list is used
        as it is); ``model``: empty = Copilot's default; ``token``: a GitHub
        token instead of the CLI's login."""
        self._command = list(command) if isinstance(command, list) else resolve(command)
        self._model = model
        self._token = token

    @property
    def available(self) -> bool:
        return self._command is not None

    def version(self) -> str | None:
        """``GitHub Copilot CLI 1.0.103.``, None when not installed or not answering."""
        if self._command is None:
            return None
        try:
            result = subprocess.run([*self._command, "--version"], capture_output=True, text=True, timeout=30, **NO_WINDOW)
        except (OSError, subprocess.TimeoutExpired):
            return None
        return result.stdout.strip().splitlines()[0] if result.returncode == 0 and result.stdout.strip() else None

    def turn(
        self,
        cwd: Path,
        session_id: str,
        prompt: str,
        mode: CopilotMode,
        timeout_seconds: float,
        denied_tools: Sequence[str] = (),
        should_cancel: Callable[[], bool] = lambda: False,
    ) -> CopilotTurn:
        """One message to the session and Copilot's answer. ``denied_tools``
        count only in execute mode. Never raises for Copilot's own failures:
        they come back in ``error``."""
        if self._command is None:
            return CopilotTurn(message="", exit_code=-1, error=NOT_FOUND)
        argv = [*self._command, *self._arguments(cwd, session_id, prompt, mode, denied_tools)]
        try:
            result = process.run(argv, cwd, self._environment(), timeout_seconds, should_cancel)
        except OSError as exc:
            return CopilotTurn(message="", exit_code=-1, error=f"Impossibile avviare Copilot CLI: {exc}")
        return to_turn(result, timeout_seconds)

    def _arguments(self, cwd: Path, session_id: str, prompt: str, mode: CopilotMode, denied_tools: Sequence[str]) -> list[str]:
        arguments = ["-p", prompt, "--session-id", session_id, "--add-dir", str(cwd), "--output-format", "json", "--no-color"]
        if mode == CopilotMode.PLAN:
            arguments += ["--mode", "plan"]
        else:
            arguments += ["--mode", "autopilot", "--allow-all-tools", "--no-ask-user"]
            for tool in denied_tools:
                arguments += ["--deny-tool", tool]
        if self._model:
            arguments += ["--model", self._model]
        return arguments

    def _environment(self) -> dict[str, str]:
        environment = {**os.environ, "NO_COLOR": "1"}
        if self._token:
            environment["COPILOT_GITHUB_TOKEN"] = self._token
        return environment
