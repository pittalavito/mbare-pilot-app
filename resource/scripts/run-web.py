"""The app with the React frontend: starts the API (unless one already answers
at API_URL) and Vite's dev server (web/) on WEB_PORT, which proxies /api to it.
The worker is started from the frontend (the API manages it).

The API's output goes to resource/logs/api.log (the frontend shows it). Closing
this script (Ctrl+C) stops what it started: the API, and with it a worker the
API started. With API_RELOAD=true the API restarts by itself when src/ changes.
Installs the frontend's dependencies the first time."""
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from utils import env_value, get_project_root, load_env

_API_START_TIMEOUT = 60.0


def run_web() -> int:
    sys.stdout.reconfigure(line_buffering=True)  # messages show at once, also when redirected
    load_env()
    npm = shutil.which("npm")
    if npm is None:
        print("npm non trovato: installa Node.js (https://nodejs.org) e riprova.")
        return 1
    root = get_project_root()
    api_url = env_value("API_URL", "http://127.0.0.1:8000").rstrip("/")

    api = None
    if _healthy(api_url):
        print(f"API già attiva su {api_url}: uso quella.")
    else:
        api = _start_api(root, api_url)
        print(f"API in avvio su {api_url} (log: resource/logs/api.log)...")
        if not _wait_healthy(api_url, api):
            print("L'API non risponde: guarda resource/logs/api.log.")
            _stop(api)
            return 1
        print("API attiva.")

    web = root / "web"
    try:
        if not (web / "node_modules").exists():
            installed = subprocess.run([npm, "install"], cwd=web)
            if installed.returncode != 0:
                return installed.returncode
        return subprocess.run([npm, "run", "dev"], cwd=web).returncode
    except KeyboardInterrupt:
        return 0
    finally:
        if api is not None:
            print("Fermo l'API.")
            _stop(api)


def _start_api(root: Path, api_url: str) -> subprocess.Popen:
    url = urlparse(api_url)
    host, port = url.hostname or "127.0.0.1", str(url.port or 8000)
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


def _healthy(api_url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{api_url}/health", timeout=1.5) as response:
            return response.status == 200
    except OSError:
        return False


def _wait_healthy(api_url: str, api: subprocess.Popen) -> bool:
    deadline = time.monotonic() + _API_START_TIMEOUT
    while time.monotonic() < deadline:
        if api.poll() is not None:
            return False  # exited: see its log
        if _healthy(api_url):
            return True
        time.sleep(0.5)
    return False


def _stop(process: subprocess.Popen) -> None:
    """The process and everything it started (uvicorn, the worker the API started)."""
    if process.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True)
    else:
        os.killpg(process.pid, signal.SIGTERM)


if __name__ == "__main__":
    sys.exit(run_web())
