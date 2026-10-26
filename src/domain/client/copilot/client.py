"""GitHub Copilot CLI as a subprocess: one turn (``copilot -p``) per call, in a
session whose id the app chooses (``--session-id``), so Copilot keeps the
conversation across calls.

Two modes:

- **plan**: ``--mode plan``. Copilot reads the code and answers; the CLI
  itself blocks every change outside its session folder.
- **execute**: ``--mode autopilot --allow-all-tools``, minus the git commands
  that touch history, index or branches (``EXECUTION_DENIED``): Copilot
  changes files, the user commits.

The output is JSONL (``--output-format json``): the answer is the last
``assistant.message`` with content, the ``result`` event has exit code and
usage. npm installs a ``.cmd`` launcher on Windows, which would cut the prompt
at its first newline: the client calls node with Copilot's script instead."""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path

import psutil

from models.domain.copilot import CopilotTurn
# todof: rifattorizzare tutta sta roba (tuttol il file non mi piace come è gestito)
EXECUTION_DENIED = [
    "shell(git commit)", "shell(git push)", "shell(git add)", "shell(git rm)", "shell(git mv)", "shell(git restore)",
    "shell(git reset)", "shell(git checkout)", "shell(git switch)", "shell(git stash)", "shell(git rebase)",
    "shell(git merge)", "shell(git cherry-pick)", "shell(git revert)", "shell(git am)", "shell(git tag)",
    "shell(git branch)", "shell(git clean)", "shell(git update-ref)", "shell(git worktree)",
]
"""Execution may change the working tree, never commits, the index or the branches."""

_POLL_SECONDS = 0.5
_ERROR_TAIL = 1500


class CopilotMode(StrEnum):
    PLAN = "plan"
    EXECUTE = "execute"


class CopilotClient:

    def __init__(self, command: str | list[str] = "copilot", model: str = "", token: str | None = None):
        """``command``: the CLI (name on the PATH or path; an argv list is used
        as it is); ``model``: empty = Copilot's default; ``token``: a GitHub
        token instead of the CLI's login."""
        self._command = list(command) if isinstance(command, list) else _resolve(command)
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
            result = subprocess.run([*self._command, "--version"], capture_output=True, text=True, timeout=30, **_NO_WINDOW)
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
        should_cancel: Callable[[], bool] = lambda: False,
    ) -> CopilotTurn:
        """One message to the session and Copilot's answer. Never raises for
        Copilot's own failures: they come back in ``error``."""
        if self._command is None:
            return CopilotTurn(message="", exit_code=-1, error="Copilot CLI non trovato: installalo (npm install -g @github/copilot) e fai il login.")
        try:
            process = subprocess.Popen(
                [*self._command, *self._arguments(cwd, session_id, prompt, mode)],
                cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                encoding="utf-8", errors="replace", env=self._environment(), **_NO_WINDOW,
            )
        except OSError as exc:
            return CopilotTurn(message="", exit_code=-1, error=f"Impossibile avviare Copilot CLI: {exc}")
        stdout, stderr = _PipeReader(process.stdout), _PipeReader(process.stderr)
        deadline = time.monotonic() + timeout_seconds
        stopped = None
        while process.poll() is None:
            if should_cancel():
                stopped = "cancelled"
            elif time.monotonic() > deadline:
                stopped = "timeout"
            if stopped:
                _kill_tree(process)
                break
            time.sleep(_POLL_SECONDS)
        process.wait()
        stdout.join(), stderr.join()
        return _turn(stdout.lines, "".join(stderr.lines), process.returncode, stopped, timeout_seconds)

    def _arguments(self, cwd: Path, session_id: str, prompt: str, mode: CopilotMode) -> list[str]:
        arguments = ["-p", prompt, "--session-id", session_id, "--add-dir", str(cwd), "--output-format", "json", "--no-color"]
        if mode == CopilotMode.PLAN:
            arguments += ["--mode", "plan"]
        else:
            arguments += ["--mode", "autopilot", "--allow-all-tools", "--no-ask-user"]
            for tool in EXECUTION_DENIED:
                arguments += ["--deny-tool", tool]
        if self._model:
            arguments += ["--model", self._model]
        return arguments

    def _environment(self) -> dict[str, str]:
        environment = {**os.environ, "NO_COLOR": "1"}
        if self._token:
            environment["COPILOT_GITHUB_TOKEN"] = self._token
        return environment


_NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
"""No console window for Copilot when the worker runs without one."""


def _resolve(command: str) -> list[str] | None:
    """The argv prefix that runs the CLI; on Windows the npm ``.cmd`` launcher
    becomes ``node <npm-loader.js>`` (a .cmd would truncate multi-line arguments)."""
    path = shutil.which(command)
    if path is None:
        return None
    if Path(path).suffix.lower() in {".cmd", ".bat"}:
        loader = Path(path).parent / "node_modules" / "@github" / "copilot" / "npm-loader.js"
        node = Path(path).parent / "node.exe" if (Path(path).parent / "node.exe").exists() else shutil.which("node")
        if loader.is_file() and node:
            return [str(node), str(loader)]
    return [path]


class _PipeReader(threading.Thread):
    """Reads a pipe to the end in the background, so a full pipe never blocks Copilot."""

    def __init__(self, pipe):
        super().__init__(daemon=True)
        self.lines: list[str] = []
        self._pipe = pipe
        self.start()

    def run(self) -> None:
        for line in self._pipe:
            self.lines.append(line)


def _kill_tree(process: subprocess.Popen) -> None:
    """Copilot and whatever it started (shells, test runs...)."""
    try:
        parent = psutil.Process(process.pid)
        for child in parent.children(recursive=True):
            child.kill()
        parent.kill()
    except psutil.NoSuchProcess:
        pass


def _turn(lines: list[str], stderr: str, returncode: int, stopped: str | None, timeout_seconds: float) -> CopilotTurn:
    message, result = "", None
    for line in lines:
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "assistant.message" and (content := (event.get("data") or {}).get("content")):
            message = content
        elif event.get("type") == "result":
            result = event
    exit_code = result.get("exitCode", returncode) if result else returncode
    premium = int(((result or {}).get("usage") or {}).get("premiumRequests") or 0)
    if stopped == "cancelled":
        return CopilotTurn(message=message, exit_code=exit_code, premium_requests=premium, error="Annullata.", cancelled=True)
    if stopped == "timeout":
        return CopilotTurn(message=message, exit_code=exit_code, premium_requests=premium, error=f"Nessuna risposta entro {timeout_seconds / 60:.0f} minuti: fermata.")
    if exit_code != 0:
        detail = stderr.strip()[-_ERROR_TAIL:] or f"exit code {exit_code}"
        return CopilotTurn(message=message, exit_code=exit_code, premium_requests=premium, error=f"Copilot CLI ha dato errore: {detail}")
    return CopilotTurn(message=message, exit_code=exit_code, premium_requests=premium)
