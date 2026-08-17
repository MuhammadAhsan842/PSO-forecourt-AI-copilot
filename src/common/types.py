"""Shared value types.

Kept dependency-free (pydantic only) so it stays cheap to import from tests.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class CameraRole(str, Enum):
    OVERVIEW = "overview"
    WIDE = "wide"
    PTZ = "ptz"
    FIXED_METER = "fixed_meter"
    FIXED_PLATE = "fixed_plate"


class EventKind(str, Enum):
    AFTER_HOURS_PRESENCE = "after_hours_presence"
    QUEUE_DWELL = "queue_dwell"
    RESTRICTED_ENTRY = "restricted_entry"
    LOITERING = "loitering"
    VEHICLE_SETTLED_AT_PUMP = "vehicle_settled_at_pump"
    DRIVE_OFF = "drive_off"
    SALE_RECORDED = "sale_recorded"
    CAMERA_OFFLINE = "camera_offline"
    CAMERA_ONLINE = "camera_online"


class Point(BaseModel):
    x: float
    y: float


class BoundingBox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def width(self) -> float:
        return max(0.0, self.x2 - self.x1)

    @property
    def height(self) -> float:
        return max(0.0, self.y2 - self.y1)

    @property
    def center(self) -> Point:
        return Point(x=(self.x1 + self.x2) / 2.0, y=(self.y1 + self.y2) / 2.0)

    @property
    def area(self) -> float:
        return self.width * self.height


class Detection(BaseModel):
    """One raw detector output on one frame."""

    class_id: int
    class_name: str
    confidence: float
    bbox: BoundingBox
    frame_ts: datetime = Field(default_factory=datetime.utcnow)


class Track(BaseModel):
    """A tracked object over time; `track_id` is stable across frames."""

    track_id: int
    class_name: str
    bbox: BoundingBox
    confidence: float
    frame_ts: datetime
    hits: int = 1
    age_seconds: float = 0.0


class EventRecord(BaseModel):
    """A single event flowing between the event engine, storage, and dashboard."""

    id: str
    kind: EventKind
    camera_id: str
    track_id: int | None = None
    zone_id: str | None = None
    confidence: float = 1.0
    snapshot_path: str | None = None
    ts: datetime = Field(default_factory=datetime.utcnow)
    payload: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class Feedback(BaseModel):
    """Human true/false-positive verdict on an event."""

    event_id: str
    verdict: Literal["true", "false"]
    note: str | None = None
    reviewer: str | None = None
    ts: datetime = Field(default_factory=datetime.utcnow)
