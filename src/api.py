"""ASGI entry point of the backend: ``uvicorn api:app --app-dir src``
(started from the UI's Backend panel). All wiring lives in core/app.py."""
from core.app import create_app

app = create_app()
