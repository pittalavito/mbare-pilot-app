"""Development: the API (unless one already answers at API_URL) and Vite's dev
server (web/) on WEB_PORT, with hot reload; Vite proxies /api to the API. For
normal use there is run-app.py (one port, the built frontend).

The worker is started from the frontend (the API manages it). Closing this
script (Ctrl+C) stops what it started: the API, and with it a worker the API
started. With API_RELOAD=true the API restarts by itself when src/ changes.
Installs the frontend's dependencies the first time."""
import shutil
import subprocess
import sys

from api_process import api_url, ensure_api, stop
from utils import get_project_root, load_env


def run_web() -> int:
    sys.stdout.reconfigure(line_buffering=True)  # messages show at once, also when redirected
    load_env()
    npm = shutil.which("npm")
    if npm is None:
        print("npm non trovato: installa Node.js (https://nodejs.org) e riprova.")
        return 1
    root = get_project_root()
    api, ok = ensure_api(root, api_url())
    if not ok:
        return 1
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
            stop(api)


if __name__ == "__main__":
    sys.exit(run_web())
