"""Aggregate stats used by the dashboard stat cards + the pilot report (M11)."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query

from src.storage import repository
from src.storage.db import DBSession, get_session

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/summary")
async def summary(
    days: int = Query(default=1, ge=1, le=90),
    session: DBSession = Depends(get_session),
) -> dict:
    since = datetime.utcnow() - timedelta(days=days)
    counts = await repository.event_counts_since(session, since)
    fb = await repository.feedback_summary_since(session, since)
    total_true = fb.get("true", 0)
    total_false = fb.get("false", 0)
    total_verdicts = total_true + total_false
    precision = (total_true / total_verdicts) if total_verdicts else None

    return {
        "since": since.isoformat() + "Z",
        "event_counts": counts,
        "feedback": {
            "true": total_true,
            "false": total_false,
            "precision": precision,
        },
    }


@router.get("/cameras")
async def camera_health(
    session: DBSession = Depends(get_session),
) -> list[dict]:
    return await repository.camera_status(session)
