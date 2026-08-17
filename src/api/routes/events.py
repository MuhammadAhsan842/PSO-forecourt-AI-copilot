"""Event list + creation.

Creation is used both by the internal event engine (M6) and by demo tools
(``scripts/replay_clip.py``) to inject synthetic events during acceptance runs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.websocket import broadcast_event
from src.common.types import EventKind, EventRecord
from src.storage import repository
from src.storage.db import DBSession, get_session

router = APIRouter(prefix="/events", tags=["events"])


class EventCreate(BaseModel):
    kind: EventKind
    camera_id: str
    track_id: int | None = None
    zone_id: str | None = None
    confidence: float = 1.0
    snapshot_path: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


@router.get("", response_model=list[EventRecord])
async def list_events(
    camera_id: str | None = None,
    kind: EventKind | None = None,
    since: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    session: DBSession = Depends(get_session),
) -> list[EventRecord]:
    return await repository.list_events(
        session,
        camera_id=camera_id,
        kind=kind,
        since=since,
        limit=limit,
    )


@router.post("", response_model=EventRecord, status_code=201)
async def create_event(
    body: EventCreate,
    session: DBSession = Depends(get_session),
) -> EventRecord:
    record = await repository.create_event(
        session,
        kind=body.kind,
        camera_id=body.camera_id,
        track_id=body.track_id,
        zone_id=body.zone_id,
        confidence=body.confidence,
        snapshot_path=body.snapshot_path,
        payload=body.payload,
    )
    await broadcast_event(record)
    return record


@router.get("/{event_id}", response_model=EventRecord)
async def get_event(
    event_id: str, session: DBSession = Depends(get_session)
) -> EventRecord:
    record = await repository.get_event(session, event_id)
    if not record:
        raise HTTPException(status_code=404, detail="event not found")
    return record
