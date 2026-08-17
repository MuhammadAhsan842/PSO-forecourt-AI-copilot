"""Milestone 6 acceptance: each rule fires on crafted inputs; cooldowns work."""

from __future__ import annotations

from datetime import datetime

from src.common.types import BoundingBox, EventKind, Track
from src.events.engine import EventEngine, ListSink


def _t(track_id: int, bbox: tuple[float, float, float, float], name: str = "car", age_s: float = 5) -> Track:
    return Track(
        track_id=track_id,
        class_name=name,
        bbox=BoundingBox(x1=bbox[0], y1=bbox[1], x2=bbox[2], y2=bbox[3]),
        confidence=0.9,
        frame_ts=datetime.utcnow(),
        hits=10,
        age_seconds=age_s,
    )


def test_restricted_entry_fires() -> None:
    engine = EventEngine(enabled_rules=["restricted_entry"], cooldown_seconds={"restricted_entry": 0})
    engine.configure_camera(
        "cam",
        zones_cfg=[
            {"id": "no-go", "kind": "restricted", "polygon": [[0, 0], [100, 0], [100, 100], [0, 100]], "entry_alert": True}
        ],
        lines_cfg=[],
    )
    tracks = [_t(1, (30, 30, 70, 90), name="person")]
    sink = ListSink()
    emitted = engine.tick("cam", tracks, sink)
    assert len(emitted) == 1
    assert emitted[0].kind == EventKind.RESTRICTED_ENTRY


def test_pump_settle_triggers_capture_event() -> None:
    engine = EventEngine(
        enabled_rules=["vehicle_settled_at_pump"],
        cooldown_seconds={"vehicle_settled_at_pump": 0},
    )
    engine.configure_camera(
        "cam",
        zones_cfg=[
            {
                "id": "bay-A",
                "kind": "pump_bay",
                "pump_id": "A",
                "polygon": [[0, 0], [200, 0], [200, 200], [0, 200]],
                "settle_seconds": 2,
            }
        ],
        lines_cfg=[],
    )
    tracks = [_t(1, (10, 10, 150, 190), name="motorcycle", age_s=5)]
    sink = ListSink()
    emitted = engine.tick("cam", tracks, sink)
    assert len(emitted) == 1
    assert emitted[0].kind == EventKind.VEHICLE_SETTLED_AT_PUMP
    assert emitted[0].payload["pump_id"] == "A"


def test_cooldown_suppresses_duplicates() -> None:
    engine = EventEngine(enabled_rules=["restricted_entry"], cooldown_seconds={"restricted_entry": 60})
    engine.configure_camera(
        "cam",
        zones_cfg=[{"id": "z", "kind": "restricted", "polygon": [[0, 0], [10, 0], [10, 10], [0, 10]]}],
        lines_cfg=[],
    )
    tracks = [_t(9, (1, 1, 5, 5), name="person")]
    sink = ListSink()
    first = engine.tick("cam", tracks, sink)
    second = engine.tick("cam", tracks, sink)
    assert len(first) == 1 and len(second) == 0
