"""The server uvicorn runs: the API under ``/api`` and, at every other path,
the React frontend built in web/dist (``npm run build``): its files, and
index.html for the pages of the app (the router of the browser handles them).

The API keeps its own paths (``create_app``): its OpenAPI schema, the client
generated from it and the tests do not know about the prefix."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from starlette.exceptions import HTTPException

from core.app import create_app
from core.container import Container

API_PREFIX = "/api"

_NOT_BUILT = """<!doctype html><meta charset="utf-8"><title>Mbare Pilot</title>
<body style="font-family: sans-serif; padding: 2rem">
<h1>Frontend non compilato</h1>
<p>L'API è attiva su <a href="/api/docs">/api</a>, ma manca <code>web/dist</code>.</p>
<p>Avvia l'app con <code>python resource/scripts/run-app.py</code> (compila il frontend se serve)
o, per lo sviluppo, <code>python resource/scripts/run-web.py</code>.</p>"""


def create_server(dist: Path, container: Container | None = None) -> FastAPI:
    """``dist`` is the built frontend; ``container`` is for tests (see create_app)."""
    api = create_app(container)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with api.router.lifespan_context(api):  # a mounted app's lifespan does not run by itself
            yield

    server = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    server.mount(API_PREFIX, api)

    @server.get("/{path:path}", include_in_schema=False)
    async def frontend(path: str):
        """A file of the build, or index.html for any other page of the app."""
        index = dist / "index.html"
        if not index.is_file():
            return HTMLResponse(_NOT_BUILT, status_code=503)
        file = (dist / path).resolve()
        if path and file.is_file() and file.is_relative_to(dist.resolve()):
            return FileResponse(file)
        if path.startswith("assets/"):  # a missing file of the build, not a page
            raise HTTPException(status_code=404)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return server
