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


# Per-channel meter LCD crops in *main-stream* (4K) pixel coords.
# Channel 9 = M1 / Pump 1. Tight crop on the 4-digit window (green panel).
# Calibrated live 2026-08-26 01:16 — reading was 0000 (idle).
_METER_ROI: dict[int, tuple[int, int, int, int]] = {
    9: (1800, 700, 220, 110),  # x, y, w, h on 3840x2160
}


def _meter_roi(channel: int) -> tuple[int, int, int, int] | None:
    try:
        from src.meter.config import meter_roi_for_channel

        roi = meter_roi_for_channel(channel)
        if roi is not None:
            return roi
    except Exception:
        pass
    return _METER_ROI.get(channel)


def _nvr_cgi_snapshot(channel: int):
    """I-frame JPEG from the NVR snapshot.cgi — sharper than a compressed RTSP frame."""
    import requests
    from requests.auth import HTTPDigestAuth

    host, user, password, _port = _creds()
    url = f"http://{host}/cgi-bin/snapshot.cgi?channel={channel}"
    r = requests.get(url, auth=HTTPDigestAuth(user, password), timeout=8)
    if r.status_code != 200 or not r.content:
        return None
    import numpy as np

    arr = np.frombuffer(r.content, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def _downscale_hq(frame, width: int):
    """Area-downsample 4K → display width. Looks far sharper than the 704px sub-stream."""
    fh, fw = frame.shape[:2]
    if width <= 0 or fw <= width:
        return frame
    height = int(fh * (width / fw))
    return cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)


def _enhance_hq(frame):
    """Denoise + unsharp. For meter crops / display, not cartoon CLAHE."""
    den = cv2.fastNlMeansDenoisingColored(frame, None, 3, 3, 7, 15)
    blur = cv2.GaussianBlur(den, (0, 0), 0.9)
    return cv2.addWeighted(den, 1.45, blur, -0.45, 0)


def _crop_and_scale(frame, x: int, y: int, w: int, h: int, scale: float, hq: bool = True):
    fh, fw = frame.shape[:2]
    x = max(0, min(x, fw - 1))
    y = max(0, min(y, fh - 1))
    w = max(1, min(w, fw - x))
    h = max(1, min(h, fh - y))
    crop = frame[y : y + h, x : x + w]
    if scale and scale != 1.0:
        interp = cv2.INTER_LANCZOS4 if hq else cv2.INTER_CUBIC
        crop = cv2.resize(crop, (int(w * scale), int(h * scale)), interpolation=interp)
    if hq:
        crop = _enhance_hq(crop)
    return crop


@router.get("/snapshot/{channel}.jpg")
async def snapshot(
    channel: int,
    subtype: int | None = None,
    q: int = 88,
    roi: str | None = None,
    scale: float = 1.0,
    hq: int = 0,
    width: int = 0,
) -> Response:
    """One fresh frame. Channel 9/10 default to the 4K main stream.

    ``roi=meter`` — NVR snapshot.cgi I-frame (sharper than RTSP) + Lanczos
    upscale + denoise/unsharp.
    ``width=1920`` — AREA-downsample 4K for a crisp dashboard live view
    (the 704×576 sub-stream is what made ch9 look muddy).
    """
    if channel < 1 or channel > 64:
        raise HTTPException(400, "channel out of range")
    meter = roi == "meter"
    use_hq = bool(hq)
    if meter:
        if _meter_roi(channel) is None:
            raise HTTPException(404, f"no meter ROI calibrated for channel {channel}")
        scale = scale if scale > 1 else 5.0

    def _grab():
        frame = None
        if meter or (use_hq and channel in {9, 10, 17}):
            frame = _nvr_cgi_snapshot(channel)
        if frame is None:
            if subtype is None:
                st = 0 if channel in {9, 10, 17} or meter else 1
            else:
                st = 0 if meter else subtype
            stream = _get_stream(channel, subtype=st)
            frame = stream.read()
        return frame

    frame = await asyncio.to_thread(_grab)
    if frame is None:
        raise HTTPException(504, "no frame from channel")
    if meter:
        x, y, w, h = _meter_roi(channel)  # type: ignore[misc]
        frame = _crop_and_scale(frame, x, y, w, h, scale, hq=use_hq)
    elif width > 0:
        frame = _downscale_hq(frame, width)
        if use_hq:
            # Light unsharp only — nlmeans on 1080p is too slow for live.
            blur = cv2.GaussianBlur(frame, (0, 0), 0.7)
            frame = cv2.addWeighted(frame, 1.25, blur, -0.25, 0)
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, int(q)])
    if not ok:
        raise HTTPException(500, "encode failed")
    return Response(
        content=buf.tobytes(),
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/mjpeg/{channel}")
async def mjpeg(
    channel: int,
    subtype: int = 1,
    fps: float = 8.0,
    q: int = 70,
    roi: str | None = None,
    scale: float = 1.0,
):
    """Live MJPEG — cropped to the meter LCD when ``roi=meter``.

    Uses the 4K main stream for meter crops so digits stay as sharp as
    this fixed camera can get. Default ~8 FPS.
    """
    if channel < 1 or channel > 64:
        raise HTTPException(400, "channel out of range")
    meter = roi == "meter"
    if meter:
        if _meter_roi(channel) is None:
            raise HTTPException(404, f"no meter ROI calibrated for channel {channel}")
        subtype = 0
        scale = scale if scale > 1 else 5.0
    stream = _get_stream(channel, subtype=subtype)
    interval = 1.0 / max(1.0, min(fps, 15.0))
    boundary = "frame"

    async def gen():
        try:
            while True:
                frame = await asyncio.to_thread(stream.read)
                if frame is None:
                    await asyncio.sleep(0.2)
                    continue
                if meter:
                    box = _meter_roi(channel)
                    if box is not None:
                        x, y, w, h = box
                        frame = _crop_and_scale(frame, x, y, w, h, scale)
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
            return

    return StreamingResponse(
        gen(),
        media_type=f"multipart/x-mixed-replace; boundary={boundary}",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Connection": "keep-alive",
        },
    )
