"""Phase 0 — optics proof CLI.

On the station LAN (or VPN). Does NOT read digits. Proves whether the meter
ROI has enough pixels during a fill to justify building the reader.

    # 1) HTTP preflight (won't hammer a locked NVR)
    # 2) optional PTZ GotoPreset (ONVIF then Dahua HTTP)
    # 3) main-stream 4K burst + ROI crops
    # 4) JSON report with PASS/FAIL pixel gate (≥600×300)

    python -m scripts.meter_optics_proof --channel 9 --no-ptz \\
        --roi 1800 700 220 110 --burst 20 --out data/meter_optics/m1_ch9

    python -m scripts.meter_optics_proof --channel 10 --preset-index 2 \\
        --roi 1800 700 400 250 --burst 30 --settle 6 \\
        --out data/meter_optics/m1_via_ch10_ptz

Reuse: URL-encoded RTSP passwords, HTTP RmLock preflight. Never skip those.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

from scripts.nvr_scan import _preflight_auth
from src.common.config import build_nvr_rtsp_url
from src.common.logging import get_logger, setup_logging
from src.meter.optics import crop_roi, optics_report
from src.meter.ptz_goto import PtzGotoError, dahua_list_presets, goto_preset

log = get_logger(__name__)


def _load_env_file(path: Path = Path(".env")) -> dict[str, str]:
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        v = v.split("#", 1)[0].strip().strip('"').strip("'")
        out[k.strip()] = v
    return out


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key) or _load_env_file().get(key, default)


def _open_cap(url: str, timeout_ms: int = 8000):
    import cv2

    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_ms)
    cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout_ms)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if not cap.isOpened():
        cap.release()
        return None
    return cap


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Phase 0 optics proof — 4K burst + meter ROI report")
    p.add_argument("--host", default=_env("CAM_PUMP_A_HOST"))
    p.add_argument("--user", default=_env("CAM_PUMP_A_USER", "admin"))
    p.add_argument("--password", default=_env("CAM_PUMP_A_PASS"))
    p.add_argument("--channel", type=int, required=True, help="NVR channel (1-based)")
    p.add_argument("--subtype", type=int, default=0, help="0=main 4K (required for the gate)")
    p.add_argument("--rtsp-port", type=int, default=554)
    p.add_argument("--http-port", type=int, default=80)
    p.add_argument("--onvif-port", type=int, default=80)
    p.add_argument("--no-ptz", action="store_true", help="skip preset slew (fixed camera)")
    p.add_argument(
        "--preset-index", type=int, default=None, help="Dahua preset index (ch10: 2=overview)"
    )
    p.add_argument("--preset-name", default=None, help="ONVIF preset name/token if available")
    p.add_argument("--skip-onvif", action="store_true")
    p.add_argument("--list-presets", action="store_true")
    p.add_argument("--settle", type=float, default=5.0, help="seconds to wait after PTZ move")
    p.add_argument("--burst", type=int, default=20)
    p.add_argument("--interval", type=float, default=0.2, help="seconds between burst frames")
    p.add_argument("--roi", nargs=4, type=int, metavar=("X", "Y", "W", "H"), default=None)
    p.add_argument("--out", type=Path, default=Path("data/meter_optics/run"))
    args = p.parse_args(argv)

    setup_logging(level="INFO", json_output=False)

    if not args.host or not args.password:
        print("need --host/--password or CAM_PUMP_A_HOST / CAM_PUMP_A_PASS in .env", flush=True)
        return 2

    ok, msg = _preflight_auth(args.host, args.user, args.password, http_port=args.http_port)
    if not ok:
        print(f"preflight FAILED: {msg}", flush=True)
        return 3
    print(f"preflight OK: {msg}", flush=True)

    if args.list_presets:
        try:
            presets = dahua_list_presets(
                host=args.host,
                user=args.user,
                password=args.password,
                channel=args.channel,
                http_port=args.http_port,
            )
            print(json.dumps(presets, indent=2))
        except PtzGotoError as exc:
            print(f"list-presets failed: {exc}", flush=True)
            return 4
        if args.list_presets and args.burst <= 0:
            return 0

    backend = None
    if not args.no_ptz and (args.preset_index is not None or args.preset_name):
        try:
            backend = goto_preset(
                host=args.host,
                user=args.user,
                password=args.password,
                channel=args.channel,
                preset_index=args.preset_index,
                preset_name=args.preset_name,
                onvif_port=args.onvif_port,
                http_port=args.http_port,
                try_onvif=not args.skip_onvif,
            )
            print(f"PTZ goto via {backend}; settling {args.settle}s", flush=True)
            time.sleep(max(0.0, args.settle))
        except PtzGotoError as exc:
            print(f"PTZ FAILED: {exc}", flush=True)
            return 5

    if args.burst <= 0:
        print("skipping capture (--burst 0)", flush=True)
        return 0

    url = build_nvr_rtsp_url(
        host=args.host,
        user=args.user,
        password=args.password,
        channel=args.channel,
        subtype=args.subtype,
        rtsp_port=args.rtsp_port,
    )
    cap = _open_cap(url)
    if cap is None:
        print("could not open RTSP main stream", flush=True)
        return 6

    import cv2

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "frames").mkdir(exist_ok=True)
    (args.out / "roi").mkdir(exist_ok=True)

    reports: list[dict] = []
    try:
        for i in range(args.burst):
            ok_f, frame = cap.read()
            if not ok_f or frame is None:
                log.warning("burst_frame_miss", extra={"context": {"i": i}})
                time.sleep(args.interval)
                continue
            ts = datetime.now(UTC).isoformat()
            fh, fw = frame.shape[:2]
            full_path = args.out / "frames" / f"frame_{i:04d}.jpg"
            cv2.imwrite(str(full_path), frame)
            entry: dict = {
                "i": i,
                "ts": ts,
                "frame_wh": [fw, fh],
                "full": str(full_path),
            }
            if args.roi:
                x, y, w, h = args.roi
                roi = crop_roi(frame, x, y, w, h)
                roi_path = args.out / "roi" / f"roi_{i:04d}.jpg"
                cv2.imwrite(str(roi_path), roi)
                entry["roi_file"] = str(roi_path)
                entry["optics"] = optics_report(roi)
            reports.append(entry)
            time.sleep(args.interval)
    finally:
        cap.release()

    if not reports:
        print("no frames captured", flush=True)
        return 7

    last_opt = next((r["optics"] for r in reversed(reports) if "optics" in r), None)
    summary = {
        "schema_version": 1,
        "captured_at": datetime.now(UTC).isoformat(),
        "host": args.host,
        "channel": args.channel,
        "subtype": args.subtype,
        "ptz_backend": backend,
        "preset_index": args.preset_index,
        "preset_name": args.preset_name,
        "roi": args.roi,
        "n_frames": len(reports),
        "last_optics": last_opt,
        "human_readable_during_fill": None,
        "note": (
            "Set human_readable_during_fill true/false after you watch a live fill. "
            "Pixel gate alone is not enough — digits must be readable while they roll."
        ),
        "frames": reports,
    }
    report_path = args.out / "optics_report.json"
    report_path.write_text(json.dumps(summary, indent=2))
    print(f"wrote {report_path}", flush=True)
    if last_opt:
        print(
            f"ROI {last_opt['roi_width']}x{last_opt['roi_height']}  "
            f"sharp={last_opt['sharpness_laplacian']}  "
            f"display_guess={last_opt['display_guess']}",
            flush=True,
        )
        print(last_opt["gate_reason"], flush=True)
        return 0 if last_opt["pass_px"] else 8
    print(
        "no --roi given; full frames only. Re-run with --roi X Y W H after you pick the meter box.",
        flush=True,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
