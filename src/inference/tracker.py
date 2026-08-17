"""Lightweight multi-object tracker.

Uses ByteTrack from Ultralytics if available (their tracker gives us stable ids
via ``model.track``). We keep a small internal IoU-based fallback so tests can
exercise the event engine deterministically without needing the ML deps.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from src.common.logging import get_logger
from src.common.types import BoundingBox, Detection, Track

log = get_logger(__name__)


def _iou(a: BoundingBox, b: BoundingBox) -> float:
    x1 = max(a.x1, b.x1)
    y1 = max(a.y1, b.y1)
    x2 = min(a.x2, b.x2)
    y2 = min(a.y2, b.y2)
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    ua = a.area + b.area - inter
    return inter / ua if ua > 0 else 0.0


@dataclass
class _State:
    track: Track
    last_seen: datetime
    misses: int = 0
    history: list[BoundingBox] = field(default_factory=list)


class Tracker:
    """Deterministic IoU-based tracker. Small enough to test in-process."""

    def __init__(
        self,
        *,
        iou_threshold: float = 0.3,
        max_age_frames: int = 30,
        min_hits: int = 3,
    ):
        self.iou_threshold = iou_threshold
        self.max_age_frames = max_age_frames
        self.min_hits = min_hits
        self._next_id: int = 1
        self._states: dict[int, _State] = {}

    def update(
        self,
        detections: Iterable[Detection],
        *,
        ts: datetime | None = None,
    ) -> list[Track]:
        ts = ts or datetime.utcnow()
        detections = list(detections)

        # Age existing tracks; remove stale
        for state in list(self._states.values()):
            state.misses += 1
        self._states = {
            tid: s
            for tid, s in self._states.items()
            if s.misses <= self.max_age_frames
        }

        # Greedy IoU match
        unassigned_det = list(range(len(detections)))
        for state in self._states.values():
            best, best_iou = -1, self.iou_threshold
            for di in unassigned_det:
                if detections[di].class_name != state.track.class_name:
                    continue
                score = _iou(state.track.bbox, detections[di].bbox)
                if score > best_iou:
                    best_iou = score
                    best = di
            if best >= 0:
                d = detections[best]
                state.track = state.track.model_copy(
                    update={
                        "bbox": d.bbox,
                        "confidence": d.confidence,
                        "frame_ts": ts,
                        "hits": state.track.hits + 1,
                    }
                )
                state.last_seen = ts
                state.misses = 0
                state.history.append(d.bbox)
                if len(state.history) > 60:
                    state.history = state.history[-60:]
                unassigned_det.remove(best)

        # Spawn new tracks for unassigned detections
        for di in unassigned_det:
            d = detections[di]
            tid = self._next_id
            self._next_id += 1
            self._states[tid] = _State(
                track=Track(
                    track_id=tid,
                    class_name=d.class_name,
                    bbox=d.bbox,
                    confidence=d.confidence,
                    frame_ts=ts,
                    hits=1,
                    age_seconds=0.0,
                ),
                last_seen=ts,
            )

        # Return active tracks that have enough hits to be considered stable
        return [s.track for s in self._states.values() if s.track.hits >= self.min_hits]

    def all_tracks(self) -> list[Track]:
        return [s.track for s in self._states.values()]

    def reset(self) -> None:
        self._states.clear()
        self._next_id = 1
