"""The app on one port: builds the frontend (web/ -> web/dist) when it is
missing or older than its sources, then starts the API (unless one already
answers at API_URL), which serves the app at / and itself at /api.

The worker is started from the app (the API manages it). Ctrl+C stops what
this script started. For development with hot reload there is run-web.py."""
import shutil
import subprocess
import sys
import time
from pathlib import Path

from api_process import api_url, ensure_api, stop
from utils import get_project_root, load_env

_SOURCES = ["src", "public", "index.html", "package.json", "package-lock.json", "vite.config.ts", "tsconfig.json"]


def run_app() -> int:
    sys.stdout.reconfigure(line_buffering=True)  # messages show at once, also when redirected
    load_env()
    root = get_project_root()
    web = root / "web"
    if _stale(web):
        built = _build(web)
        if built != 0:
            return built
    url = api_url()
    api, ok = ensure_api(root, url)
    if not ok:
        return 1
    print(f"Mbare Pilot: {url}")
    if api is None:
        return 0  # already running elsewhere: nothing to keep alive here
    try:
        while api.poll() is None:
            time.sleep(1)
        print("L'API si è fermata: guarda resource/logs/api.log.")
        return api.returncode or 1
    except KeyboardInterrupt:
        return 0
    finally:
        print("Fermo l'API.")
        stop(api)


def _stale(web: Path) -> bool:
    """No build yet, or a source of the frontend changed after it."""
    index = web / "dist" / "index.html"
    if not index.exists():
        return True
    built_at = index.stat().st_mtime
    for name in _SOURCES:
        source = web / name
        files = source.rglob("*") if source.is_dir() else [source]
        if any(path.is_file() and path.stat().st_mtime > built_at for path in files):
            return True
    return False


def _build(web: Path) -> int:
    npm = shutil.which("npm")
    if npm is None:
        print("npm non trovato: installa Node.js (https://nodejs.org) e riprova.")
        return 1
    if not (web / "node_modules").exists():
        installed = subprocess.run([npm, "install"], cwd=web)
        if installed.returncode != 0:
            return installed.returncode
    print("Compilo il frontend (web/dist)...")
    return subprocess.run([npm, "run", "build"], cwd=web).returncode


if __name__ == "__main__":
    sys.exit(run_app())
