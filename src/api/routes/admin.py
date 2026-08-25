"""Admin routes: retention purge (the §9 privacy control, made operable)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from src.storage.retention import run_retention_purge

router = APIRouter(tags=["admin"], prefix="/admin")


@router.post("/purge")
async def purge(
    retention_days: int | None = Query(
        default=None,
        ge=0,
        description="Override the configured retention window (days). Omit to use config.",
    ),
) -> dict:
    """Delete events/feedback/readings and snapshot folders older than the window.

    Intended to be scheduled daily on-site; exposed here so staff can also run it
    on demand and see exactly what was removed.
    """
    return await run_retention_purge(retention_days)
