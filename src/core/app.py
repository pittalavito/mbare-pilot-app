"""Application factory: builds and wires the FastAPI app in one place.
src/api.py exposes ``app = create_app()`` for uvicorn. The app's MCP server
for Copilot is mounted here at ``/mcp`` (controller/mcp_server.py)."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError

from config import Config
from controller.mcp_server import build_mcp_server, mcp_app
from controller.router import router as api_router
from core.container import Container
from core.error import AppError, ConflictError, NotFoundError, UpstreamError, ValidationError
from core.observability import configure_logging

_STATUS: dict[type[AppError], int] = {
    NotFoundError: 404,
    ValidationError: 400,
    ConflictError: 409,
    UpstreamError: 502,
}


def create_app(container: Container | None = None) -> FastAPI:
    """The API. ``container`` is for tests; by default it is built at startup
    from the Config (Postgres, Redis, ...)."""

    mcp = build_mcp_server(lambda: app.state.container.copilot_service, lambda: app.state.container.rag_service)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if container is None:
            configure_logging(Config.get().app_log_level)
        app.state.container = container or Container()
        async with mcp.session_manager.run():  # the MCP server (mounted at /mcp) needs its task group
            yield

    app = FastAPI(title="Mbare Pilot API", lifespan=lifespan)

    @app.exception_handler(AppError)
    async def on_app_error(request: Request, exc: AppError) -> JSONResponse:
        """Expected failures become 4xx/5xx with the message for the UI."""
        status = next((code for kind, code in _STATUS.items() if isinstance(exc, kind)), 500)
        return JSONResponse(status_code=status, content={"detail": str(exc)})

    @app.exception_handler(PydanticValidationError)
    async def on_domain_validation_error(request: Request, exc: PydanticValidationError) -> JSONResponse:
        """A domain model rejected the data (e.g. an invalid model key): 400 with
        the first reason. Invalid request bodies are FastAPI's own 422."""
        error = exc.errors()[0]
        field = ".".join(str(part) for part in error.get("loc", ()))
        return JSONResponse(status_code=400, content={"detail": f"{field}: {error['msg']}" if field else error["msg"]})

    app.include_router(api_router)
    app.mount("/mcp", mcp_app(mcp))  # Copilot's tools while it works on a task (controller/mcp_server.py)
    return app
