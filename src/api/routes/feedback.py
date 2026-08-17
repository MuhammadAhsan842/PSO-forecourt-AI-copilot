"""Human true/false feedback on events. Feeds the metrics loop (M11)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.common.types import Feedback
from src.storage import repository
from src.storage.db import DBSession, get_session

router = APIRouter(prefix="/feedback", tags=["feedback"])


class FeedbackCreate(BaseModel):
    event_id: str
    verdict: Literal["true", "false"]
    note: str | None = None
    reviewer: str | None = None


@router.post("", response_model=Feedback, status_code=201)
async def submit_feedback(
    body: FeedbackCreate, session: DBSession = Depends(get_session)
) -> Feedback:
    if not await repository.get_event(session, body.event_id):
        raise HTTPException(status_code=404, detail="event not found")
    return await repository.record_feedback(
        session,
        event_id=body.event_id,
        verdict=body.verdict,
        note=body.note,
        reviewer=body.reviewer,
    )
