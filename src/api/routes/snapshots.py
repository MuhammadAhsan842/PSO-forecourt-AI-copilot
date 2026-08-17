"""Snapshot serving.

The bulk of snapshot access goes through the ``/snapshots`` StaticFiles mount in
``main.py``. This router exposes a lookup by event id, which handles the DB
translation from ``snapshot_path`` (relative) to URL.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from src.common.config import get_settings
from src.storage import repository
from src.storage.db import DBSession, get_session

router = APIRouter(prefix="/snapshots", tags=["snapshots"])


@router.get("/event/{event_id}")
async def snapshot_for_event(
    event_id: str, session: DBSession = Depends(get_session)
) -> FileResponse:
    event = await repository.get_event(session, event_id)
    if not event or not event.snapshot_path:
        raise HTTPException(status_code=404, detail="no snapshot for event")

    root = get_settings().snapshot_dir
    path = (root / event.snapshot_path).resolve()
    if not path.exists() or (root.resolve() not in path.parents and path != root.resolve()):
        raise HTTPException(status_code=404, detail="snapshot missing")

    return FileResponse(path)
