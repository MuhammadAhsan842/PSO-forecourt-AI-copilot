"""NVR channel manifest + live MJPEG stream.

* ``GET /nvr/channels`` — reads the JSON manifest written by
  ``scripts/nvr_scan`` so the dashboard can pick up a fresh scan without an
  API restart. Image files are served by the ``/nvr-stills`` StaticFiles
  mount registered in ``main.py``.
* ``GET /nvr/mjpeg/{channel}`` — opens the channel's RTSP stream and
  streams JPEG frames as ``multipart/x-mixed-replace`` so a browser
  ``<img>`` tag can render live video natively (no HLS/WebRTC needed).
* ``GET /nvr/snapshot/{channel}.jpg`` — one fresh JPEG frame. Used when
  MJPEG is overkill or the client just wants a poll-refresh view.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

import cv2
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import StreamingResponse

from src.common.config import build_nvr_rtsp_url
from src.common.logging import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/nvr", tags=["nvr"])


def _manifest_path() -> Path:
    return Path("data/nvr_scan/manifest.json")


def _load_env_file(path: Path = Path(".env")) -> dict[str, str]:
    """Tiny .env parser for the CAM_PUMP_A_* creds.

    We can't reuse pydantic-settings here because that class uses a
    ``PSO_`` prefix; the camera creds are prefix-less by convention
    (they're shared with the shell scripts). Ignores comments, quoted
    values, and blank lines.
    """
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        # Strip inline comments and quotes.
        v = v.split("#", 1)[0].strip().strip('"').strip("'")
        out[k.strip()] = v
    return out


def _env(key: str, default: str = "") -> str:
    """Prefer real env vars, fall back to .env file."""
    v = os.environ.get(key)
    if v:
        return v
    return _load_env_file().get(key, default)


def _creds() -> tuple[str, str, str, int]:
    """Resolve host/user/password/port from environment.

    The RTSP scanner and PTZ scripts already use ``CAM_PUMP_A_*``; we
    reuse the same convention here so a single ``.env`` drives everything.
    """
    host = _env("CAM_PUMP_A_HOST")
    user = _env("CAM_PUMP_A_USER", "admin")
    password = _env("CAM_PUMP_A_PASS", "")
    port = int(_env("CAM_PUMP_A_RTSP_PORT", "554"))
    if not host:
        raise HTTPException(
            status_code=503,
            detail="CAM_PUMP_A_HOST not set — cannot stream (check .env)",
        )
    return host, user, password, port


# --------------------------------------------------------------------------
# Simple per-channel capture cache. OpenCV VideoCapture is expensive to
# open (2-3 s over RTSP) so we keep one open per channel and hand out
# frames from a shared queue-of-one. Not thread-safe for concurrent
# .read() calls, so we grab a lock per channel. Enough for the pilot's
# small number of dashboard clients.
# --------------------------------------------------------------------------
class _ChannelStream:
    def __init__(self, channel: int, subtype: int = 1):
        self.channel = channel
        self.subtype = subtype
        self._cap: cv2.VideoCapture | None = None
        self._lock = threading.Lock()
        self._last_frame: Any = None
        self._last_read_at: float = 0.0

    def _open(self) -> cv2.VideoCapture:
        host, user, password, port = _creds()
        url = build_nvr_rtsp_url(
            host=host, user=user, password=password,
            channel=self.channel, subtype=self.subtype, rtsp_port=port,
        )
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000)
        # Keep a small queue so we always serve the freshest frame.
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not cap.isOpened():
            raise HTTPException(
                status_code=504,
                detail=f"could not open RTSP for channel {self.channel}",
            )
        return cap

    def read(self):
        with self._lock:
            if self._cap is None:
                self._cap = self._open()
            ok, frame = self._cap.read()
            if not ok or frame is None:
                # Stream stalled — reopen once and retry.
                self._cap.release()
                self._cap = self._open()
                ok, frame = self._cap.read()
                if not ok or frame is None:
                    return None
            self._last_frame = frame
            self._last_read_at = time.time()
            return frame

    def close(self):
        with self._lock:
            if self._cap is not None:
                self._cap.release()
                self._cap = None


_streams: dict[int, _ChannelStream] = {}
_streams_lock = threading.Lock()


def _get_stream(channel: int, subtype: int = 1) -> _ChannelStream:
    key = channel * 10 + subtype
    with _streams_lock:
        s = _streams.get(key)
        if s is None:
            s = _ChannelStream(channel, subtype=subtype)
            _streams[key] = s
        return s


@router.get("/channels")
async def list_channels() -> dict:
    p = _manifest_path()
    if not p.exists():
        raise HTTPException(
            status_code=404,
            detail="no NVR scan yet — run `python -m scripts.nvr_scan`",
        )
    return json.loads(p.read_text())


@router.get("/snapshot/{channel}.jpg")
async def snapshot(channel: int, subtype: int = 1, q: int = 75) -> Response:
    """One fresh frame from a channel. Cheap poll-refresh path."""
    if channel < 1 or channel > 64:
        raise HTTPException(400, "channel out of range")
    stream = _get_stream(channel, subtype=subtype)
    frame = await asyncio.to_thread(stream.read)
    if frame is None:
        raise HTTPException(504, "no frame from channel")
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, int(q)])
    if not ok:
        raise HTTPException(500, "encode failed")
    return Response(
        content=buf.tobytes(),
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/mjpeg/{channel}")
async def mjpeg(channel: int, subtype: int = 1, fps: float = 8.0, q: int = 70):
    """MJPEG stream — one JPEG per frame in multipart/x-mixed-replace.

    Renders live in a bare ``<img>`` tag. Default 8 FPS / q=70 keeps the
    bandwidth honest for a laptop over the site LAN; bump ``fps`` for a
    smoother view or ``q`` for a sharper one.
    """
    if channel < 1 or channel > 64:
        raise HTTPException(400, "channel out of range")
    stream = _get_stream(channel, subtype=subtype)
    interval = 1.0 / max(1.0, min(fps, 25.0))
    boundary = "frame"

    async def gen():
        try:
            while True:
                frame = await asyncio.to_thread(stream.read)
                if frame is None:
                    await asyncio.sleep(0.5)
                    continue
                ok, buf = cv2.imencode(
                    ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, int(q)]
                )
                if not ok:
                    continue
                jpg = buf.tobytes()
                yield (
                    b"--" + boundary.encode() + b"\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(jpg)).encode() + b"\r\n\r\n"
                    + jpg + b"\r\n"
                )
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            # Client disconnected — nothing to do; the shared capture
            # stays open for the next viewer.
            return

    return StreamingResponse(
        gen(),
        media_type=f"multipart/x-mixed-replace; boundary={boundary}",
        headers={"Cache-Control": "no-store"},
    )
