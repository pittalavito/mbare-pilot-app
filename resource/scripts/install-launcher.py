"""Makes the launcher (launcher.py) start by itself when you log in, in the
background, starts it now and opens its page: save it in the browser's
favourites and from then on start and stop the app from there.

    python resource/scripts/install-launcher.py            install
    python resource/scripts/install-launcher.py --remove   uninstall

Windows: a script in the Startup folder. macOS: a LaunchAgent. Linux: an
entry in ~/.config/autostart. Run it again after moving the repository."""
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

from utils import get_project_root

ROOT = get_project_root()
LAUNCHER = ROOT / "resource" / "scripts" / "launcher.py"
NAME = "mbare-pilot-launcher"


def _env(name: str, default: str) -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines() if (ROOT / ".env").is_file() else []:
        if line.strip().startswith(f"{name}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'") or default
    return default


def _env_url() -> str:
    return _env("LAUNCHER_URL", "http://127.0.0.1:8090").rstrip("/") + "/"


def _python(windowless: bool) -> Path:
    if sys.platform == "win32":
        return ROOT / ".venv" / "Scripts" / ("pythonw.exe" if windowless else "python.exe")
    return ROOT / ".venv" / "bin" / "python"


def _autostart_file() -> Path:
    home = Path.home()
    if sys.platform == "win32":
        return Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup" / f"{NAME}.vbs"
    if sys.platform == "darwin":
        return home / "Library/LaunchAgents" / f"com.{NAME}.plist"
    return home / ".config/autostart" / f"{NAME}.desktop"


def _autostart_content() -> str:
    python, script = _python(windowless=True), LAUNCHER
    if sys.platform == "win32":
        # WScript.Shell.Run with 0: no window at all
        return (f'CreateObject("WScript.Shell").Run """{python}"" ""{script}""", 0, False\r\n')
    if sys.platform == "darwin":
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.{NAME}</string>
  <key>ProgramArguments</key><array><string>{python}</string><string>{script}</string></array>
  <key>WorkingDirectory</key><string>{ROOT}</string>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:{Path.home()}/.local/bin</string></dict>
  <key>RunAtLoad</key><true/>
</dict></plist>
"""
    return f"""[Desktop Entry]
Type=Application
Name=Mbare Pilot launcher
Exec="{python}" "{script}"
Path={ROOT}
Terminal=false
X-GNOME-Autostart-enabled=true
"""


def _start_now() -> None:
    """Started detached, as the login would."""
    command = [str(_python(windowless=True)), str(LAUNCHER)]
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(command, cwd=ROOT, creationflags=flags, close_fds=True)
    elif sys.platform == "darwin":
        subprocess.run(["launchctl", "unload", str(_autostart_file())], capture_output=True)
        subprocess.run(["launchctl", "load", str(_autostart_file())], check=False)
    else:
        subprocess.Popen(command, cwd=ROOT, start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def install() -> int:
    if not _python(windowless=True).exists():
        print("Manca .venv: lancia prima `python resource/scripts/start-venv.py` (vedi README).")
        return 1
    if not (ROOT / ".env").is_file():
        print("Manca .env: copialo da .env.example (vedi README), poi riprova.")
        return 1
    api = _env("API_URL", "http://127.0.0.1:8000")
    if (urlparse(api).port or 8000) == (urlparse(_env_url()).port or 8090):
        print(f"API_URL ({api}) e LAUNCHER_URL ({_env_url()}) usano la stessa porta: nel .env metti")
        print("LAUNCHER_URL su un'altra porta, es. LAUNCHER_URL=http://127.0.0.1:8091, e riprova.")
        return 1
    target = _autostart_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_autostart_content(), encoding="utf-8")
    print(f"Avvio automatico al login: {target}")
    _start_now()
    url = _env_url()
    time.sleep(2)
    webbrowser.open(url)
    print(f"Launcher attivo: {url}  ← salvalo nei preferiti del browser.")
    return 0


def remove() -> int:
    target = _autostart_file()
    if sys.platform == "darwin" and target.exists():
        subprocess.run(["launchctl", "unload", str(target)], capture_output=True)
    if target.exists():
        target.unlink()
        print(f"Tolto l'avvio automatico ({target}).")
    else:
        print("L'avvio automatico non era installato.")
    print("Se il launcher è attivo si ferma al prossimo riavvio (o chiudi il suo processo python).")
    return 0


if __name__ == "__main__":
    sys.exit(remove() if "--remove" in sys.argv else install())
