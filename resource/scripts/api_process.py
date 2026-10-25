"""The API process, shared by run-app.py and run-web.py: started in the
background with its output in resource/logs/api.log (the frontend shows it),
checked through /api/health, stopped with everything it started."""
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from utils import env_value

_START_TIMEOUT = 60.0


def api_url() -> str:
    """Where the server answers (API_URL): the app at /, the API at /api."""
    return env_value("API_URL", "http://127.0.0.1:8000").rstrip("/")


def start_api(root: Path, url: str) -> subprocess.Popen:
    """uvicorn on the host and port of ``url``; with API_RELOAD=true it restarts when src/ changes."""
    address = urlparse(url)
    host, port = address.hostname or "127.0.0.1", str(address.port or 8000)
    app, app_dir = env_value("API_APP", "api:app"), env_value("API_APP_DIR", "src")
    python = str(root / (".venv/Scripts/python.exe" if sys.platform == "win32" else ".venv/bin/python"))
    if os.environ.get("API_RELOAD", "").lower() == "true":
        command = [python, str(root / "resource" / "scripts" / "api_reloader.py"), app, app_dir, host, port]
    else:
        command = [python, "-m", "uvicorn", app, "--app-dir", app_dir, "--host", host, "--port", port]
    logs = root / "resource" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    with (logs / "api.log").open("ab") as log:
        return subprocess.Popen(
            command, cwd=root, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
            **({} if sys.platform == "win32" else {"start_new_session": True}),
        )


def healthy(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/api/health", timeout=1.5) as response:
            return response.status == 200
    except OSError:
        return False


def wait_healthy(url: str, api: subprocess.Popen) -> bool:
    deadline = time.monotonic() + _START_TIMEOUT
    while time.monotonic() < deadline:
        if api.poll() is not None:
            return False  # exited: see its log
        if healthy(url):
            return True
        time.sleep(0.5)
    return False


def stop(process: subprocess.Popen) -> None:
    """The process and everything it started (uvicorn, the worker the API started)."""
    if process.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True)
    else:
        os.killpg(process.pid, signal.SIGTERM)


def ensure_api(root: Path, url: str) -> tuple[subprocess.Popen | None, bool]:
    """The API at ``url``: the one already answering, or a new one. Returns the
    process started here (None when one was already running) and whether it answers."""
    if healthy(url):
        print(f"API già attiva su {url}: uso quella.")
        return None, True
    api = start_api(root, url)
    print(f"API in avvio su {url} (log: resource/logs/api.log)...")
    if not wait_healthy(url, api):
        print("L'API non risponde: guarda resource/logs/api.log.")
        stop(api)
        return None, False
    print("API attiva.")
    return api, True
