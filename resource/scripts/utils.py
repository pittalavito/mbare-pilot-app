"""Shared helpers for the operational scripts in resource/scripts/."""
import os
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def get_project_root() -> Path:
    return PROJECT_ROOT


def uv_command() -> list[str]:
    """The uv executable, or ``python -m uv`` when it is not on PATH."""
    uv = shutil.which("uv")
    return [uv] if uv else [sys.executable, "-m", "uv"]


def load_env() -> None:
    """Load the repo-root .env into os.environ. Imported lazily so the venv
    bootstrap script (which runs before dependencies exist) can import utils."""
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")


def env_value(name: str, default: str) -> str:
    value = os.environ.get(name, default)
    if value == default:
        print(f"WARNING: Environment variable {name} not set, using default: {default}")
    return value
