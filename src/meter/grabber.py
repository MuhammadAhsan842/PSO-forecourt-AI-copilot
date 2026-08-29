"""Latest-frame grabber — wraps ``IngestWorker``, does not open a second RTSP stack."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from src.common.config import CameraConfig
from src.ingest.worker import FrameSample, IngestWorker


class FrameSource(Protocol):
    def start(self) -> None: ...
    def stop(self, timeout: float = 5.0) -> None: ...
    def latest(self) -> FrameSample | None: ...


class MeterGrabber:
    """Watchdog around ingest: stale() is true if the last frame is too old."""

    def __init__(
        self,
        camera: CameraConfig | None = None,
        *,
        source: FrameSource | None = None,
        target_fps: int = 5,
        stale_after_s: float = 3.0,
    ):
        if source is None and camera is None:
            raise ValueError("MeterGrabber needs a CameraConfig or an injected source")
        self._source: FrameSource = source or IngestWorker(camera, target_fps=target_fps)
        self.stale_after_s = stale_after_s

    def start(self) -> None:
        self._source.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._source.stop(timeout=timeout)

    def latest(self) -> FrameSample | None:
        return self._source.latest()

    def stale(self, now: datetime | None = None) -> bool:
        sample = self.latest()
        if sample is None:
            return True
        now = now or datetime.now(UTC)
        ts = sample.ts
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        return (now - ts).total_seconds() > self.stale_after_s
