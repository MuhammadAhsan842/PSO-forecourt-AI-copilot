"""SQLAlchemy ORM models — SQLite (WAL) for the pilot."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class EventRow(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String, index=True)
    camera_id: Mapped[str] = mapped_column(String, index=True)
    track_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    zone_id: Mapped[str | None] = mapped_column(String, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    snapshot_path: Mapped[str | None] = mapped_column(String, nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)

    feedback: Mapped[list[FeedbackRow]] = relationship(back_populates="event")


class FeedbackRow(Base):
    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    event_id: Mapped[str] = mapped_column(String, ForeignKey("events.id"), index=True)
    verdict: Mapped[str] = mapped_column(String)  # "true" | "false"
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    reviewer: Mapped[str | None] = mapped_column(String, nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    event: Mapped[EventRow] = relationship(back_populates="feedback")


class ReadingRow(Base):
    """A meter or plate reading tied to (optionally) a track / event."""

    __tablename__ = "readings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    camera_id: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String, index=True)  # "meter" | "plate"
    track_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    event_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    value: Mapped[str] = mapped_column(String)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class CameraHealthRow(Base):
    __tablename__ = "camera_health"

    camera_id: Mapped[str] = mapped_column(String, primary_key=True)
    online: Mapped[bool] = mapped_column(default=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
