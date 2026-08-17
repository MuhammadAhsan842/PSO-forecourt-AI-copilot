"""System routes: liveness / build info."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter

from src import __version__
from src.common.config import get_settings

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "time": datetime.utcnow().isoformat() + "Z",
        "service": "pso-surveillance",
    }


@router.get("/version")
async def version() -> dict:
    return {"version": __version__, "timezone": get_settings().timezone}
