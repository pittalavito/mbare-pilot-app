"""Frontend: the React app (web/) on WEB_PORT, with Vite's dev server: /api is
proxied to the API at API_URL. Installs the dependencies the first time.
For now the API and the worker are started as before (Streamlit's Backend
panel); this script will start the API too once the React app replaces it."""
import shutil
import subprocess
import sys

from utils import get_project_root, load_env


def run_web() -> int:
    load_env()
    npm = shutil.which("npm")
    if npm is None:
        print("npm non trovato: installa Node.js (https://nodejs.org) e riprova.")
        return 1
    web = get_project_root() / "web"
    if not (web / "node_modules").exists():
        installed = subprocess.run([npm, "install"], cwd=web)
        if installed.returncode != 0:
            return installed.returncode
    return subprocess.run([npm, "run", "dev"], cwd=web).returncode


if __name__ == "__main__":
    sys.exit(run_web())
