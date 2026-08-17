"""Tracker sanity: one moving object keeps one id across frames."""

from __future__ import annotations

from datetime import datetime, timedelta

from src.common.types import BoundingBox, Detection
from src.inference.tracker import Tracker


def _det(x: float, y: float, w: float = 60, h: float = 40, name: str = "car") -> Detection:
    return Detection(
        class_id=2,
        class_name=name,
        confidence=0.9,
        bbox=BoundingBox(x1=x, y1=y, x2=x + w, y2=y + h),
    )


def test_single_object_keeps_one_id() -> None:
    tracker = Tracker(iou_threshold=0.1, max_age_frames=10, min_hits=1)
    ts = datetime(2026, 8, 17, 12, 0, 0)
    tracks = []
    for step in range(10):
        d = _det(100 + step * 5, 200)
        tracks = tracker.update([d], ts=ts + timedelta(milliseconds=step * 100))
    assert len(tracks) == 1
    assert tracks[0].hits == 10


def test_two_objects_get_distinct_ids() -> None:
    tracker = Tracker(iou_threshold=0.2, max_age_frames=10, min_hits=1)
    ts = datetime.utcnow()
    tracks = tracker.update([_det(50, 50), _det(500, 500)], ts=ts)
    ids = {t.track_id for t in tracks}
    assert len(ids) == 2
