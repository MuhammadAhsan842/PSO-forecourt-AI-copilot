"""FastAPI entry point.

M0 acceptance: ``GET /health`` returns 200 with build info.
Extended in M7 with events, snapshots, feedback, WebSocket live feed.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src import __version__
from src.api.routes import admin, events, feedback, snapshots, stats, system
from src.api.websocket import register_websocket
from src.common.config import get_settings, load_settings_yaml
from src.common.logging import get_logger, setup_logging
from src.storage.db import init_db

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    yaml_settings = _safe_load_yaml_settings()
    log_conf = (yaml_settings or {}).get("logging", {})
    setup_logging(
        level=log_conf.get("level", settings.log_level),
        json_output=bool(log_conf.get("json", True)),
    )
    log.info(
        "app_start",
        extra={"context": {"version": __version__, "timezone": settings.timezone}},
    )
    await init_db(settings.db_url)
    settings.snapshot_dir.mkdir(parents=True, exist_ok=True)
    yield
    log.info("app_stop")


def _safe_load_yaml_settings() -> dict | None:
    try:
        return load_settings_yaml()
    except Exception as exc:      # pragma: no cover - only hit when config is broken
        print(f"[warn] could not load settings.yaml: {exc}")
        return None


def create_app() -> FastAPI:
    settings = get_settings()
    yaml_settings = _safe_load_yaml_settings() or {}
    cors_origins = yaml_settings.get("api", {}).get(
        "cors_origins", ["http://localhost:5173"]
    )

    app = FastAPI(
        title="PSO Forecourt AI Surveillance",
        version=__version__,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(system.router)
    app.include_router(events.router, prefix="/api/v1")
    app.include_router(feedback.router, prefix="/api/v1")
    app.include_router(snapshots.router, prefix="/api/v1")
    app.include_router(stats.router, prefix="/api/v1")
    app.include_router(admin.router, prefix="/api/v1")

    register_websocket(app, path=yaml_settings.get("api", {}).get(
        "websocket_path", "/ws/events"
    ))

    snapshot_dir = settings.snapshot_dir
    if snapshot_dir.exists():
        app.mount(
            "/snapshots",
            StaticFiles(directory=str(snapshot_dir)),
            name="snapshots",
        )

    return app


app = create_app()


def run() -> None:
    """Entry point for ``pso-api`` console script."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "src.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )


# For ``python -m src.api.main``
if __name__ == "__main__":       # pragma: no cover
    asyncio.get_event_loop().run_until_complete(asyncio.sleep(0))
    run()
