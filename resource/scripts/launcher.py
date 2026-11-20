"""Launcher: a small local server that starts and stops the app from a page in
the browser, without terminals. It serves launcher.html on LAUNCHER_URL
(default http://127.0.0.1:8090): save that page in the browser's favourites.

"Avvia" does what the README does by hand: Docker (Postgres and Redis, starting
Docker Desktop when it is off), the frontend build when it is missing or old,
then the API on API_URL. "Ferma" stops the API (and the worker it started);
"Ferma Docker" stops the containers too. Its log is local/logs/launcher.log.

It runs with the .venv python (it reuses api_process and python-dotenv), in the
background: install-launcher.py makes it start by itself when you log in.

    .venv/bin/python resource/scripts/launcher.py      (Windows: .venv\\Scripts\\pythonw.exe)
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from api_process import healthy, start_api, stop, wait_healthy
from utils import get_project_root, load_env

ROOT = get_project_root()
HERE = Path(__file__).resolve().parent
LOG = ROOT / "local" / "logs" / "launcher.log"
COMPOSE = ["compose", "--env-file", ".env", "-f", "resource/docker/docker-compose.yml"]
NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
DOCKER_DESKTOP_TIMEOUT = 180.0


def _run_app_module():
    """run-app.py has a dash in its name: loaded by path for its _stale check."""
    spec = importlib.util.spec_from_file_location("run_app", HERE / "run-app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Launcher:
    """What the page drives: one action at a time, its progress in ``step``."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.busy = False
        self.step = ""
        self.error = ""
        self.api: subprocess.Popen | None = None

    # ---- log ---------------------------------------------------------------

    def log(self, message: str) -> None:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as out:
            out.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {message}\n")

    def _say(self, message: str) -> None:
        self.step = message
        self.log(message)

    def _command(self, command: list[str], cwd: Path) -> int:
        """A command with its output in the launcher log."""
        self.log("$ " + " ".join(command))
        with LOG.open("ab") as out:
            return subprocess.run(
                command, cwd=cwd, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, **NO_WINDOW,
            ).returncode

    # ---- state -------------------------------------------------------------

    def status(self) -> dict:
        url = api_url_quiet()
        ours = self.api is not None and self.api.poll() is None
        return {
            "busy": self.busy,
            "step": self.step,
            "error": self.error,
            "api": healthy(url),
            "api_ours": ours,
            "app_url": url,
            "docker": self._docker_running(),
        }

    def _docker_running(self) -> bool | None:
        docker = shutil.which("docker")
        if docker is None:
            return None
        try:
            out = subprocess.run(
                [docker, *COMPOSE, "ps", "--status", "running", "-q"], cwd=ROOT,
                capture_output=True, timeout=5, **NO_WINDOW,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return out.returncode == 0 and bool(out.stdout.strip())

    # ---- actions -----------------------------------------------------------

    def run(self, action: str) -> bool:
        """Starts ``action`` in the background; False when one is already running."""
        with self.lock:
            if self.busy:
                return False
            self.busy, self.error = True, ""
        threading.Thread(target=self._do, args=(action,), daemon=True).start()
        return True

    def _do(self, action: str) -> None:
        try:
            {"start": self._start, "stop": self._stop, "stop-all": self._stop_all}[action]()
        except Exception as exc:  # shown on the page, the details in the log
            self.error = str(exc) or exc.__class__.__name__
            self.log(f"Errore: {exc!r}")
        finally:
            self.step = ""
            self.busy = False

    def _start(self) -> None:
        load_env()
        url = api_url_quiet()
        if not (ROOT / ".env").is_file():
            raise RuntimeError(".env non trovato: copialo da .env.example (vedi README).")
        self._ensure_docker()
        self._say("Avvio Postgres e Redis...")
        if self._command([shutil.which("docker"), *COMPOSE, "up", "-d", "--wait"], ROOT) != 0:
            raise RuntimeError("docker compose non è partito: guarda il log del launcher.")
        web = ROOT / "web"
        if _run_app_module()._stale(web):
            self._build(web)
        if healthy(url):
            self._say(f"API già attiva su {url}.")
            return
        self._say("Avvio l'API...")
        api = start_api(ROOT, url)
        if not wait_healthy(url, api):
            stop(api)
            raise RuntimeError("L'API non risponde: guarda local/logs/api.log.")
        self.api = api
        self._say(f"Mbare Pilot attivo su {url}.")

    def _ensure_docker(self) -> None:
        docker = shutil.which("docker")
        if docker is None:
            raise RuntimeError("docker non trovato: installa Docker Desktop.")
        if self._docker_ready(docker):
            return
        self._say("Docker è spento: lo accendo (può volerci un minuto)...")
        if sys.platform == "win32":
            desktop = Path(r"C:\Program Files\Docker\Docker\Docker Desktop.exe")
            if desktop.exists():
                subprocess.Popen([str(desktop)], **NO_WINDOW)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-a", "Docker"])
        else:
            subprocess.run(["systemctl", "--user", "start", "docker-desktop"], capture_output=True)
        deadline = time.monotonic() + DOCKER_DESKTOP_TIMEOUT
        while time.monotonic() < deadline:
            if self._docker_ready(docker):
                return
            time.sleep(3)
        raise RuntimeError("Docker non risponde: avvia Docker Desktop e riprova.")

    def _docker_ready(self, docker: str) -> bool:
        try:
            return subprocess.run([docker, "info"], capture_output=True, timeout=15, **NO_WINDOW).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def _build(self, web: Path) -> None:
        npm = shutil.which("npm")
        if npm is None:
            raise RuntimeError("npm non trovato: installa Node.js (https://nodejs.org).")
        if not (web / "node_modules").exists():
            self._say("Installo le dipendenze del frontend...")
            if self._command([npm, "install"], web) != 0:
                raise RuntimeError("npm install è fallito: guarda il log del launcher.")
        self._say("Compilo il frontend...")
        if self._command([npm, "run", "build"], web) != 0:
            raise RuntimeError("La build del frontend è fallita: guarda il log del launcher.")

    def _stop(self) -> None:
        if self.api is not None and self.api.poll() is None:
            self._say("Fermo l'API...")
            stop(self.api)
            self.api = None
            self._say("API ferma.")
        elif healthy(api_url_quiet()):
            raise RuntimeError("L'API è stata avviata fuori dal launcher (da un terminale): fermala da lì.")

    def _stop_all(self) -> None:
        self._stop()
        docker = shutil.which("docker")
        if docker:
            self._say("Fermo Postgres e Redis...")
            self._command([docker, *COMPOSE, "stop"], ROOT)
            self._say("Tutto fermo.")

    def log_tail(self, lines: int = 80) -> str:
        if not LOG.exists():
            return ""
        with LOG.open("rb") as file:
            file.seek(0, 2)
            file.seek(max(0, file.tell() - 32_000))
            text = file.read().decode("utf-8", errors="replace")
        return "\n".join(text.splitlines()[-lines:])


def api_url_quiet() -> str:
    """Like api_process.api_url(), without its warning on every poll."""
    return os.environ.get("API_URL", "http://127.0.0.1:8000").rstrip("/")


def make_handler(launcher: Launcher, allowed_hosts: set[str]):
    page = HERE / "launcher.html"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # no console: quiet
            pass

        def _allowed(self) -> bool:
            # Host check against DNS rebinding; the custom header on POSTs forces a CORS
            # preflight that is never allowed, so other sites cannot press the buttons.
            return self.headers.get("Host", "") in allowed_hosts

        def _send(self, code: int, body: bytes, kind: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data: dict, code: int = 200) -> None:
            self._send(code, json.dumps(data).encode(), "application/json")

        def do_GET(self) -> None:
            if not self._allowed():
                return self._send(403, b"forbidden", "text/plain")
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                return self._send(200, page.read_bytes(), "text/html; charset=utf-8")
            if path == "/status":
                return self._json(launcher.status())
            if path == "/log":
                return self._send(200, launcher.log_tail().encode(), "text/plain; charset=utf-8")
            self._send(404, b"not found", "text/plain")

        def do_POST(self) -> None:
            if not self._allowed() or self.headers.get("X-Launcher") != "1":
                return self._send(403, b"forbidden", "text/plain")
            action = urlparse(self.path).path.strip("/")
            if action not in ("start", "stop", "stop-all"):
                return self._send(404, b"not found", "text/plain")
            if not launcher.run(action):
                return self._json({"ok": False, "error": "C'è già un'operazione in corso."}, 409)
            self._json({"ok": True})

    return Handler


def main() -> int:
    load_env()
    address = urlparse(os.environ.get("LAUNCHER_URL", "http://127.0.0.1:8090"))
    host, port = address.hostname or "127.0.0.1", address.port or 8090
    launcher = Launcher()
    allowed = {f"{host}:{port}", f"localhost:{port}", f"127.0.0.1:{port}"}
    try:
        server = ThreadingHTTPServer((host, port), make_handler(launcher, allowed))
    except OSError:
        launcher.log(f"Porta {port} occupata: il launcher è già attivo?")
        if "--open" in sys.argv:
            webbrowser.open(f"http://{host}:{port}/")
        return 0
    launcher.log(f"Launcher attivo su http://{host}:{port}/")
    if "--open" in sys.argv:
        webbrowser.open(f"http://{host}:{port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
