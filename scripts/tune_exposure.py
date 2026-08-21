"""M1/M2 — tune exposure/WDR FROM CODE and capture the meter, glare vs no-glare.

Run on the station LAN (or via VPN to the on-site box). For each exposure/WDR
combination in the sweep it: applies the setting over the Dahua HTTP CGI, waits
for the sensor to settle, grabs a still, and saves a full frame + a zoomed crop
of the meter ROI. Ends by restoring auto-exposure so the camera is left as found.

This turns "can we make the meter readable?" into a folder of before/after crops
you can eyeball and show PSO — the M2 gate, driven from our code, not the NVR menu.

    # reads NVR creds from .env; --meter is the meter box on the analytics frame
    python -m scripts.tune_exposure --camera pump_a --meter 1380 40 250 90

    # camera behind the NVR virtual host (per-channel mapped port):
    python -m scripts.tune_exposure --camera pump_a --vhost-port 65001 --meter 1380 40 250 90

First run without --meter to just dump full frames and read off the meter box.
"""

from __future__ import annotations

import argparse
import contextlib
import time
from pathlib import Path

import numpy as np

from src.cameractl.controller import CameraController, ControlError
from src.common.config import CameraConfig, load_cameras
from src.common.logging import get_logger, setup_logging

log = get_logger(__name__)

# (label, shutter, gain, wdr, wdr_value, backlight). Ordered dim→bright so the
# glary display is tamed first. Shutter strings are what Dahua CGI accepts.
DEFAULT_SWEEP: list[tuple] = [
    ("auto",            None,      None, None,  0,  None),
    ("fast_1_500",      "1/500",   0,    False, 0,  None),
    ("fast_1_1000",     "1/1000",  0,    False, 0,  None),
    ("fast_1_2000",     "1/2000",  0,    False, 0,  None),
    ("wdr_1_1000",      "1/1000",  0,    True,  60, None),
    ("wdr_hi_1_2000",   "1/2000",  0,    True,  80, None),
    ("blc_1_1000",      "1/1000",  0,    False, 0,  "blc"),
]


def _decode_jpeg(data: bytes):
    import cv2

    arr = np.frombuffer(data, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def _sharpness(gray) -> float:
    import cv2

    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def run_sweep(
    cam: CameraConfig,
    *,
    meter: tuple[int, int, int, int] | None,
    out_dir: Path,
    settle_s: float,
) -> list[dict]:
    import cv2

    ctrl = CameraController(cam)
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []

    # Show the current config once — reveals the real key schema for this firmware.
    try:
        current = ctrl._http_client().get_config("VideoInExposure")
        log.info("current_exposure_config", extra={"context": {"keys": len(current)}})
        (out_dir / "current_exposure_config.txt").write_text(
            "\n".join(f"{k}={v}" for k, v in current.items())
        )
    except ControlError as exc:
        log.warning("could_not_read_config", extra={"context": {"err": str(exc)}})

    for label, shutter, gain, wdr, wdr_value, backlight in DEFAULT_SWEEP:
        try:
            ctrl.set_exposure_http(
                mode="auto" if label == "auto" else "manual",
                shutter=shutter, gain=gain, wdr=wdr, wdr_value=wdr_value, backlight=backlight,
            )
        except ControlError as exc:
            log.warning("apply_failed", extra={"context": {"label": label, "err": str(exc)}})
            results.append({"label": label, "applied": False, "reason": str(exc)})
            continue

        time.sleep(settle_s)  # let the sensor settle

        try:
            frame = _decode_jpeg(ctrl.snapshot_http())
        except ControlError as exc:
            results.append({"label": label, "applied": True, "captured": False, "reason": str(exc)})
            continue
        if frame is None:
            results.append({"label": label, "applied": True, "captured": False, "reason": "decode failed"})
            continue

        cv2.imwrite(str(out_dir / f"{label}_full.jpg"), frame)
        row: dict = {"label": label, "applied": True, "captured": True}
        if meter:
            x, y, w, h = meter
            crop = frame[y : y + h, x : x + w]
            if crop.size:
                # Upscale the crop 4x so the meter is easy to eyeball.
                big = cv2.resize(crop, (w * 4, h * 4), interpolation=cv2.INTER_NEAREST)
                cv2.imwrite(str(out_dir / f"{label}_meter.jpg"), big)
                gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
                row["meter_sharpness"] = round(_sharpness(gray), 1)
                row["meter_mean"] = round(float(gray.mean()), 1)  # <250 = not clipped white
        results.append(row)
        log.info("swept", extra={"context": row})

    # Leave the camera as we found it.
    with contextlib.suppress(ControlError):
        ctrl.set_exposure_http(mode="auto")
    return results


def _print_table(results: list[dict]) -> None:
    print(f"{'SETTING':<16} {'APPLIED':<8} {'CAPTURED':<9} {'SHARPNESS':<10} {'MEAN(clip?)':<12}")
    print("-" * 60)
    for r in results:
        print(
            f"{r['label']:<16} {r.get('applied', False)!s:<8} "
            f"{r.get('captured', '-')!s:<9} {r.get('meter_sharpness', '-')!s:<10} "
            f"{r.get('meter_mean', '-')!s:<12}"
        )
    print(
        "\nLower MEAN (well under 250) = display no longer clipped to white → digits present.\n"
        "Higher SHARPNESS = crisper edges. Eyeball the *_meter.jpg crops to make the call."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sweep exposure/WDR and capture the meter (M2).")
    parser.add_argument("--camera", required=True, help="camera id from cameras.yaml")
    parser.add_argument(
        "--meter", type=int, nargs=4, metavar=("X", "Y", "W", "H"),
        help="meter ROI box on the frame; omit on the first run to dump full frames",
    )
    parser.add_argument("--vhost-port", type=int, default=None, help="NVR virtual-host port for this camera")
    parser.add_argument("--settle", type=float, default=1.5, help="seconds to wait after each change")
    parser.add_argument("--out", type=Path, default=Path("data/exposure_tuning"))
    args = parser.parse_args(argv)

    setup_logging(level="INFO", json_output=False)

    cams = [c for c in load_cameras() if c.id == args.camera]
    if not cams:
        print(f"no camera with id={args.camera} in cameras.yaml")
        return 2
    cam = cams[0]
    if args.vhost_port:
        cam.vhost_port = args.vhost_port

    meter = tuple(args.meter) if args.meter else None
    results = run_sweep(cam, meter=meter, out_dir=args.out, settle_s=args.settle)
    _print_table(results)
    print(f"\nStills saved under {args.out}/ — compare the *_meter.jpg crops.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
