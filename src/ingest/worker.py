"""RTSP ingest worker with reconnect + FPS sampling.

Milestone 4 acceptance: frames from all cameras for ≥30 minutes without a crash;
auto-recovers a dropped stream. Runs one worker per camera in a thread; the
inference loop pulls the latest ``FrameSample`` from ``latest()``.

We deliberately avoid a queue: the AI is not real-time critical (5-10 FPS).
Latest-frame-wins prevents any backlog. Callers pull when they're ready.
"""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from src.common.config import CameraConfig
from src.common.logging import get_logger

log = get_logger(__name__)


@dataclass
class FrameSample:
    camera_id: str
    ts: datetime
    frame: np.ndarray
    seq: int


class IngestWorker:
    """One camera in, latest-frame-out. Reconnects on drop with backoff."""

    def __init__(
        self,
        camera: CameraConfig,
        target_fps: int = 8,
        on_status: Callable[[str, bool, str | None], None] | None = None,
    ):
        self.camera = camera
        self.target_fps = max(1, target_fps)
        self.on_status = on_status
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._latest: FrameSample | None = None
        self._seq = 0
        self._backoff_seconds = 1.0

    # ------- lifecycle -----------------------------------------------------

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name=f"ingest-{self.camera.id}", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)

    def latest(self) -> FrameSample | None:
        with self._lock:
            return self._latest

    # ------- guts ----------------------------------------------------------

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._loop_once()
            except Exception as exc:
                log.exception(
                    "ingest_loop_error",
                    extra={"camera_id": self.camera.id, "context": {"err": str(exc)}},
                )
                self._notify_status(online=False, error=str(exc))
                self._sleep_backoff()

    def _loop_once(self) -> None:
        cap = self._open_capture()
        if cap is None:
            self._sleep_backoff()
            return

        self._backoff_seconds = 1.0
        self._notify_status(online=True, error=None)
        period = 1.0 / self.target_fps
        last_grab = 0.0

        while not self._stop.is_set():
            now = time.time()
            if now - last_grab < period:
                # Consume the buffered frames so we don't drift behind
                with contextlib.suppress(Exception):
                    cap.grab()
                time.sleep(0.01)
                continue

            ok, frame = cap.read()
            if not ok or frame is None:
                log.warning(
                    "ingest_read_failed",
                    extra={"camera_id": self.camera.id, "context": {"seq": self._seq}},
                )
                self._notify_status(online=False, error="stream ended")
                with contextlib.suppress(Exception):
                    cap.release()
                self._sleep_backoff()
                return

            last_grab = now
            self._seq += 1
            sample = FrameSample(
                camera_id=self.camera.id,
                ts=datetime.utcnow(),
                frame=frame,
                seq=self._seq,
            )
            with self._lock:
                self._latest = sample

        with contextlib.suppress(Exception):
            cap.release()

    def _open_capture(self):    # returns cv2.VideoCapture | None
        try:
            import cv2
        except Exception as exc:
            log.exception(
                "opencv_missing",
                extra={"camera_id": self.camera.id, "context": {"err": str(exc)}},
            )
            return None

        if not self.camera.rtsp_url:
            log.warning(
                "ingest_no_rtsp",
                extra={"camera_id": self.camera.id, "context": {"env": self.camera.rtsp_env}},
            )
            return None

        cap = cv2.VideoCapture(self.camera.rtsp_url, cv2.CAP_FFMPEG)
        with contextlib.suppress(Exception):
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not cap.isOpened():
            log.warning(
                "ingest_open_failed", extra={"camera_id": self.camera.id}
            )
            return None

        log.info("ingest_open_ok", extra={"camera_id": self.camera.id})
        return cap

    def _notify_status(self, online: bool, error: str | None) -> None:
        if self.on_status is None:
            return
        try:
            self.on_status(self.camera.id, online, error)
        except Exception as exc:
            log.debug(
                "status_callback_error",
                extra={"camera_id": self.camera.id, "context": {"err": str(exc)}},
            )

    def _sleep_backoff(self) -> None:
        wait = min(self._backoff_seconds, 30.0)
        log.info(
            "ingest_reconnect_wait",
            extra={"camera_id": self.camera.id, "context": {"seconds": wait}},
        )
        self._stop.wait(wait)
        self._backoff_seconds = min(30.0, self._backoff_seconds * 2)
