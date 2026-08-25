"""Pull a live still from each NVR channel — "show me all the cameras".

Run this ON A MACHINE ON THE SAME LAN as the Dahua NVR. It walks the recorder's
channels, grabs one frame from each over RTSP, and saves it so you can see what
every camera shows and pick the pump/meter-facing channel by eye.

    # uses NVR host/creds from .env (CAM_PUMP_A_HOST / _USER / _PASS)
    python -m scripts.nvr_scan

    # or pass them explicitly, scan channels 1-16, save stills under data/nvr_scan/
    python -m scripts.nvr_scan --host 192.168.1.114 --user admin --password 'admin@123' \
                               --channels 16 --out data/nvr_scan

    # just one channel, main 4K stream
    python -m scripts.nvr_scan --channel 1 --subtype 0

Prints a table of which channels responded and at what resolution. Nothing here
reaches the camera controls — it only reads streams (safe, read-only).
"""

from __future__ import annotations

import argparse
import contextlib
import os
from pathlib import Path

import requests
from requests.auth import HTTPDigestAuth

from src.common.config import build_nvr_rtsp_url
from src.common.logging import get_logger, setup_logging

log = get_logger(__name__)


def _preflight_auth(host: str, user: str, password: str, http_port: int = 80) -> tuple[bool, str]:
    """HTTP-check the NVR credentials before hammering RTSP.

    Returns ``(ok, message)``. Uses Dahua's magicBox getSystemInfo — cheap
    and doesn't touch any camera. If the response body contains ``RmLock``
    the account is temporarily locked (brute-force protection); we abort
    early with the remaining lock time so we don't extend it.
    """
    url = f"http://{host}:{http_port}/cgi-bin/magicBox.cgi?action=getSystemInfo"
    try:
        r = requests.get(url, auth=HTTPDigestAuth(user, password), timeout=5)
    except requests.RequestException as exc:
        return False, f"HTTP unreachable ({exc})"
    body = r.text or ""
    if "RmLock" in body:
        secs = 0
        for line in body.splitlines():
            if "RmLock" in line:
                with contextlib.suppress(ValueError):
                    secs = int(line.split(":")[1].strip().rstrip(","))
        mins = secs // 60
        return False, (
            f"NVR admin account is LOCKED (~{mins} min remaining, {secs}s). "
            "Clear it on the NVR local console (Main Menu -> Account) or wait it out. "
            "Do NOT retry now or the lockout will extend."
        )
    if r.status_code == 401:
        return False, "401 Unauthorized — wrong username/password."
    if r.status_code == 403:
        return False, "403 Forbidden — account exists but lacks permission (try a different user)."
    if r.status_code != 200:
        return False, f"HTTP {r.status_code} — unexpected: {body[:120]}"
    return True, body.strip().splitlines()[0] if body else "ok"


def _grab_frame(rtsp_url: str, open_timeout_ms: int = 5000):
    """Open an RTSP URL and return one frame (or None). Never raises."""
    try:
        import cv2
    except Exception as exc:  # pragma: no cover
        raise SystemExit(f"OpenCV required: pip install opencv-python-headless ({exc})") from exc

    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    try:
        # Best-effort open timeout (supported on most FFmpeg builds).
        try:
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, open_timeout_ms)
            cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, open_timeout_ms)
        except Exception:
            pass
        if not cap.isOpened():
            return None
        ok, frame = cap.read()
        return frame if ok else None
    finally:
        cap.release()


def scan(
    *,
    host: str,
    user: str | None,
    password: str | None,
    channels: list[int],
    subtype: int,
    rtsp_port: int,
    out_dir: Path,
) -> list[dict]:
    import cv2

    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    for ch in channels:
        url = build_nvr_rtsp_url(
            host=host, user=user, password=password,
            channel=ch, subtype=subtype, rtsp_port=rtsp_port,
        )
        frame = _grab_frame(url)
        if frame is None:
            results.append({"channel": ch, "live": False, "resolution": None, "still": None})
            log.warning("channel_no_signal", extra={"context": {"channel": ch}})
            continue
        h, w = frame.shape[:2]
        still = out_dir / f"channel_{ch:02d}.jpg"
        cv2.imwrite(str(still), frame)
        results.append(
            {"channel": ch, "live": True, "resolution": f"{w}x{h}", "still": str(still)}
        )
        log.info("channel_live", extra={"context": {"channel": ch, "res": f"{w}x{h}"}})
    return results


def _print_table(results: list[dict]) -> None:
    print(f"{'CH':>3}  {'LIVE':<5} {'RESOLUTION':<12} STILL")
    print("-" * 60)
    for r in results:
        print(
            f"{r['channel']:>3}  {'yes' if r['live'] else 'no':<5} "
            f"{(r['resolution'] or '-'):<12} {r['still'] or '-'}"
        )
    live = sum(1 for r in results if r["live"])
    print(f"\n{live}/{len(results)} channels live. Open the stills to pick the pump channel.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Snapshot every NVR channel.")
    parser.add_argument("--host", default=os.environ.get("CAM_PUMP_A_HOST"))
    parser.add_argument("--user", default=os.environ.get("CAM_PUMP_A_USER", "admin"))
    parser.add_argument("--password", default=os.environ.get("CAM_PUMP_A_PASS"))
    parser.add_argument("--channels", type=int, default=16, help="scan channels 1..N")
    parser.add_argument("--channel", type=int, default=None, help="scan just this channel")
    parser.add_argument("--subtype", type=int, default=1, help="0=main 4K, 1=sub-stream (faster)")
    parser.add_argument("--rtsp-port", type=int, default=554)
    parser.add_argument("--out", type=Path, default=Path("data/nvr_scan"))
    args = parser.parse_args(argv)

    setup_logging(level="INFO", json_output=False)

    if not args.host:
        print("no NVR host — set CAM_PUMP_A_HOST in .env or pass --host", flush=True)
        return 2

    if args.user and args.password:
        ok, msg = _preflight_auth(args.host, args.user, args.password)
        if not ok:
            print(f"preflight FAILED: {msg}", flush=True)
            return 3
        print(f"preflight OK: {msg}", flush=True)

    channels = [args.channel] if args.channel else list(range(1, args.channels + 1))
    results = scan(
        host=args.host, user=args.user, password=args.password,
        channels=channels, subtype=args.subtype, rtsp_port=args.rtsp_port, out_dir=args.out,
    )
    _print_table(results)
    return 0 if any(r["live"] for r in results) else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
