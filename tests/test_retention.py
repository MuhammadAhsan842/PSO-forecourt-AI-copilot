"""Retention purge removes old DB rows (events + their feedback) past the window."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.storage import repository
from src.storage.db import dispose, get_session, init_db
from src.storage.models import EventRow, FeedbackRow


@pytest.mark.asyncio
async def test_purge_removes_old_rows_keeps_recent() -> None:
    await init_db("sqlite+aiosqlite:///:memory:")
    now = datetime.utcnow()
    old = now - timedelta(days=40)

    async for session in get_session():
        # One old event (with feedback) and one recent event.
        old_ev = EventRow(id="old", kind="drive_off", camera_id="ptz1", ts=old, payload={})
        new_ev = EventRow(id="new", kind="drive_off", camera_id="ptz1", ts=now, payload={})
        session.add_all([old_ev, new_ev])
        await session.commit()
        session.add(FeedbackRow(event_id="old", verdict="true", ts=old))
        await session.commit()

        removed = await repository.purge_rows_older_than(session, now - timedelta(days=30))
        assert removed["events"] == 1
        assert removed["feedback"] == 1

        remaining = await repository.list_events(session, limit=100)
        assert [e.id for e in remaining] == ["new"]
        break

    await dispose()
