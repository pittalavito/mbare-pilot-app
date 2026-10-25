"""ASGI entry point of the backend: ``uvicorn api:app --app-dir src``. The
API answers under /api, the built frontend at every other path (core/server.py)."""
from config import Config
from core.server import create_server

app = create_server(Config.get().web_dist)
