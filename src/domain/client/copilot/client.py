"""GitHub Copilot CLI as a subprocess: one turn (``copilot -p``) per call, in a
session whose id the app chooses (``--session-id``), so Copilot keeps the
conversation across calls.

Two modes:

- **plan**: ``--mode plan``. Copilot reads the code and answers; the CLI
  itself blocks every change outside its session folder.
- **execute**: ``--mode autopilot --allow-all-tools``, minus the tools the
  caller denies (``denied_tools``, from the coding-agent definition).

Every turn also asks for the usage file (``--usage-output-file``, in a temp
folder): the session's totals come back in ``CopilotTurn.usage``.

With ``mcp`` the turn gets the app's MCP server (``--additional-mcp-config``,
a file in the same temp folder, so the token is not on the command line) and
its tools are allowed in both modes (``--allow-tool mbare-pilot``).

Finding the CLI is in cli.py, running it in process.py, reading its output
in output.py and its usage file in usage.py."""
import json
import os
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from domain.client.copilot import process
from domain.client.copilot.cli import NO_WINDOW, resolve
from domain.client.copilot.output import to_turn
from domain.client.copilot.usage import read_usage
from models.domain.copilot import CopilotTurn

NOT_FOUND = "Copilot CLI non trovato: installalo (npm install -g @github/copilot) e fai il login."


MCP_SERVER = "mbare-pilot"
"""The name Copilot knows the app's MCP server by (its tools: ``mbare-pilot/read_task``...)."""


class CopilotMode(StrEnum):
    PLAN = "plan"
    EXECUTE = "execute"


@dataclass(frozen=True)
class McpAccess:
    """The app's MCP server for one session: where it answers and the session's token."""
    url: str
    token: str

    def config(self) -> dict:
        """What ``--additional-mcp-config`` reads."""
        return {"mcpServers": {MCP_SERVER: {
            "type": "http", "url": self.url, "headers": {"Authorization": f"Bearer {self.token}"}, "tools": ["*"],
        }}}


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

    @property
    def model(self) -> str:
        """The default model; ``""`` = Copilot's own."""
        return self._model

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
        model: str = "",
        mcp: McpAccess | None = None,
    ) -> CopilotTurn:
        """One message to the session and Copilot's answer. ``denied_tools``
        count only in execute mode; ``model`` overrides the default; ``mcp``:
        the app's MCP server for this session. Never raises for Copilot's own failures: they come back in ``error``."""
        if self._command is None:
            return CopilotTurn(message="", exit_code=-1, error=NOT_FOUND)
        with tempfile.TemporaryDirectory(prefix="mbare-copilot-") as folder:
            usage_file = Path(folder) / "usage.json"
            argv = [*self._command, *self._arguments(cwd, session_id, prompt, mode, denied_tools, model or self._model),
                    "--usage-output-file", str(usage_file)]
            if mcp is not None:
                config = Path(folder) / "mcp.json"
                config.write_text(json.dumps(mcp.config()), encoding="utf-8")
                argv += ["--additional-mcp-config", f"@{config}", "--allow-tool", MCP_SERVER]
            try:
                result = process.run(argv, cwd, self._environment(), timeout_seconds, should_cancel)
            except OSError as exc:
                return CopilotTurn(message="", exit_code=-1, error=f"Impossibile avviare Copilot CLI: {exc}")
            usage, used_model = read_usage(usage_file)
        return to_turn(result, timeout_seconds).model_copy(update={"usage": usage, "model": used_model})

    def _arguments(self, cwd: Path, session_id: str, prompt: str, mode: CopilotMode, denied_tools: Sequence[str], model: str) -> list[str]:
        arguments = ["-p", prompt, "--session-id", session_id, "--add-dir", str(cwd), "--output-format", "json", "--no-color"]
        if mode == CopilotMode.PLAN:
            arguments += ["--mode", "plan"]
        else:
            arguments += ["--mode", "autopilot", "--allow-all-tools", "--no-ask-user"]
            for tool in denied_tools:
                arguments += ["--deny-tool", tool]
        if model:
            arguments += ["--model", model]
        return arguments

    def _environment(self) -> dict[str, str]:
        environment = {**os.environ, "NO_COLOR": "1"}
        if self._token:
            environment["COPILOT_GITHUB_TOKEN"] = self._token
        return environment
