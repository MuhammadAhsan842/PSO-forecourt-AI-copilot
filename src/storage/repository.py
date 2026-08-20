"""Thin data-access helpers over the ORM.

Keeps SQL out of the route handlers and lets tests stub or replace persistence
without touching the API layer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select

from src.common.types import EventKind, EventRecord, Feedback
from src.storage.db import DBSession
from src.storage.models import CameraHealthRow, EventRow, FeedbackRow, ReadingRow


def _row_to_event(row: EventRow) -> EventRecord:
    return EventRecord(
        id=row.id,
        kind=EventKind(row.kind),
        camera_id=row.camera_id,
        track_id=row.track_id,
        zone_id=row.zone_id,
        confidence=row.confidence,
        snapshot_path=row.snapshot_path,
        ts=row.ts,
        payload=row.payload or {},
    )


async def create_event(
    session: DBSession,
    *,
    kind: EventKind,
    camera_id: str,
    track_id: int | None = None,
    zone_id: str | None = None,
    confidence: float = 1.0,
    snapshot_path: str | None = None,
    payload: dict[str, Any] | None = None,
) -> EventRecord:
    row = EventRow(
        kind=kind.value,
        camera_id=camera_id,
        track_id=track_id,
        zone_id=zone_id,
        confidence=confidence,
        snapshot_path=snapshot_path,
        payload=payload or {},
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _row_to_event(row)


async def get_event(session: DBSession, event_id: str) -> EventRecord | None:
    row = await session.get(EventRow, event_id)
    return _row_to_event(row) if row else None


async def list_events(
    session: DBSession,
    *,
    camera_id: str | None = None,
    kind: EventKind | None = None,
    since: datetime | None = None,
    limit: int = 100,
) -> list[EventRecord]:
    stmt = select(EventRow).order_by(EventRow.ts.desc()).limit(limit)
    if camera_id:
        stmt = stmt.where(EventRow.camera_id == camera_id)
    if kind:
        stmt = stmt.where(EventRow.kind == kind.value)
    if since:
        stmt = stmt.where(EventRow.ts >= since)
    result = await session.execute(stmt)
    return [_row_to_event(row) for row in result.scalars().all()]


async def event_counts_since(session: DBSession, since: datetime) -> dict[str, int]:
    stmt = (
        select(EventRow.kind, func.count())
        .where(EventRow.ts >= since)
        .group_by(EventRow.kind)
    )
    rows = (await session.execute(stmt)).all()
    return {k: int(c) for k, c in rows}


async def record_feedback(
    session: DBSession,
    *,
    event_id: str,
    verdict: str,
    note: str | None = None,
    reviewer: str | None = None,
) -> Feedback:
    row = FeedbackRow(
        event_id=event_id, verdict=verdict, note=note, reviewer=reviewer
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return Feedback(
        event_id=row.event_id,
        verdict=row.verdict,  # type: ignore[arg-type]
        note=row.note,
        reviewer=row.reviewer,
        ts=row.ts,
    )


async def feedback_summary_since(
    session: DBSession, since: datetime
) -> dict[str, int]:
    stmt = (
        select(FeedbackRow.verdict, func.count())
        .where(FeedbackRow.ts >= since)
        .group_by(FeedbackRow.verdict)
    )
    rows = (await session.execute(stmt)).all()
    return {v: int(c) for v, c in rows}


async def feedback_by_kind_since(
    session: DBSession, since: datetime
) -> dict[str, dict[str, int]]:
    """Per event-kind true/false counts, joining feedback to its event.

    This is what makes precision real in the pilot report — a verdict is attached
    to an event, and an event has a kind, so precision must be computed per kind.
    """
    stmt = (
        select(EventRow.kind, FeedbackRow.verdict, func.count())
        .join(FeedbackRow, FeedbackRow.event_id == EventRow.id)
        .where(FeedbackRow.ts >= since)
        .group_by(EventRow.kind, FeedbackRow.verdict)
    )
    rows = (await session.execute(stmt)).all()
    out: dict[str, dict[str, int]] = {}
    for kind, verdict, count in rows:
        bucket = out.setdefault(kind, {"true": 0, "false": 0})
        if verdict in bucket:
            bucket[verdict] = int(count)
    return out


async def purge_rows_older_than(session: DBSession, cutoff: datetime) -> dict[str, int]:
    """Delete events/feedback/readings with ts < cutoff. Returns per-table counts.

    Feedback is removed first to respect the events FK. This is the DB half of the
    §9 retention policy; the snapshot half lives in ``storage.snapshots``.
    """
    removed: dict[str, int] = {}

    old_event_ids = (
        await session.execute(select(EventRow.id).where(EventRow.ts < cutoff))
    ).scalars().all()
    if old_event_ids:
        r = await session.execute(
            delete(FeedbackRow).where(FeedbackRow.event_id.in_(old_event_ids))
        )
        removed["feedback"] = int(r.rowcount or 0)

    r = await session.execute(delete(ReadingRow).where(ReadingRow.ts < cutoff))
    removed["readings"] = int(r.rowcount or 0)

    r = await session.execute(delete(EventRow).where(EventRow.ts < cutoff))
    removed["events"] = int(r.rowcount or 0)

    await session.commit()
    return removed


async def camera_status(session: DBSession) -> list[dict[str, Any]]:
    rows = (await session.execute(select(CameraHealthRow))).scalars().all()
    return [
        {
            "camera_id": r.camera_id,
            "online": r.online,
            "last_seen": r.last_seen.isoformat() + "Z",
            "last_error": r.last_error,
        }
        for r in rows
    ]


async def upsert_camera_health(
    session: DBSession,
    *,
    camera_id: str,
    online: bool,
    error: str | None = None,
) -> None:
    row = await session.get(CameraHealthRow, camera_id)
    if row is None:
        row = CameraHealthRow(camera_id=camera_id, online=online, last_error=error)
        session.add(row)
    else:
        row.online = online
        row.last_error = error
        row.last_seen = datetime.utcnow()
    await session.commit()
