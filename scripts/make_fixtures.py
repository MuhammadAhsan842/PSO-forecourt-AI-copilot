"""Generate SYNTHETIC day/night demo clips so the whole pipeline runs offline.

The plan (§12) says progress must never depend on live cameras: ``replay_clip.py``
runs against saved clips. Until we have real footage from a confirmed-readable
capture, these procedurally-drawn clips let us exercise detection → tracking →
events → choreographed capture → meter reading end-to-end on CI and on a laptop.

These are **clearly synthetic** and are NOT a data source for any accuracy claim —
they render a moving "vehicle" block and a seven-seg pump meter that counts up
through a sale, so the reader has something real (but honest) to decode. Real
accuracy numbers come only from on-site footage (§0, §10).

Usage:
    python -m scripts.make_fixtures --label day   --out tests/fixtures/pump_A_day.mp4
    python -m scripts.make_fixtures --label night --out tests/fixtures/pump_A_night.mp4
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from src.common.logging import get_logger, setup_logging
from src.ocr.seven_seg import render_seven_seg

log = get_logger(__name__)

# Analytics-frame size matching config/zones.yaml (ptz1: 1920x1080). We render at
# a lighter resolution to keep fixtures small; zones scale by ratio in tests.
W, H = 960, 540


def _bg(label: str) -> np.ndarray:
    base = 60 if label == "night" else 150
    frame = np.full((H, W, 3), base, dtype=np.uint8)
    # forecourt apron band
    frame[int(H * 0.55) :, :] = base - 20
    return frame


def _paste(frame: np.ndarray, patch: np.ndarray, x: int, y: int) -> None:
    ph, pw = patch.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + pw), min(H, y + ph)
    if x1 <= x0 or y1 <= y0:
        return
    frame[y0:y1, x0:x1] = patch[y0 - y : y1 - y, x0 - x : x1 - x]


# Fixed per-field digit counts (6-digit amount, 5-digit litres, 5-digit rate),
# each with 2 decimals. This is the "fixed per pump" ROI layout the plan calls for.
_FIELD_DIGITS = {"amount": 6, "litres": 5, "rate": 5}
_FIELD_ORDER = ("amount", "litres", "rate")
_PAD = 8  # panel inner padding / inter-field gap
_METER_X, _METER_Y = int(W * 0.72), int(H * 0.06)


def _field_img(name: str, value: float) -> np.ndarray:
    n = _FIELD_DIGITS[name]
    return render_seven_seg(f"{round(value * 100):0{n}d}")


def meter_rois() -> dict[str, list[int]]:
    """Authoritative [x, y, w, h] ROI per field, in analytics-frame pixels.

    Written to the fixture sidecar so replay/tests crop the exact field a real
    per-pump ``ocr`` config would carry — no pixel guessing.
    """
    rois: dict[str, list[int]] = {}
    y = _METER_Y + _PAD
    for name in _FIELD_ORDER:
        img = _field_img(name, 0.0)
        h, w = img.shape[:2]
        rois[name] = [_METER_X + _PAD, y, w, h]
        y += h + _PAD
    return rois


def _meter_patch(amount: float, litres: float, rate: float, label: str) -> np.ndarray:
    """A three-field seven-seg meter panel (Amount / Litres / Rate)."""
    fields = {"amount": amount, "litres": litres, "rate": rate}
    imgs = {name: _field_img(name, val) for name, val in fields.items()}
    panel_w = max(im.shape[1] for im in imgs.values()) + 2 * _PAD
    panel_h = sum(im.shape[0] for im in imgs.values()) + (len(imgs) + 1) * _PAD
    panel = np.full((panel_h, panel_w, 3), 12, dtype=np.uint8)
    y = _PAD
    for name in _FIELD_ORDER:
        _paste(panel, imgs[name], _PAD, y)
        y += imgs[name].shape[0] + _PAD
    if label == "night":
        panel = (panel * 0.9).astype(np.uint8)  # slightly dimmer bezel at night
    return panel


def _vehicle_patch(t: float) -> np.ndarray:
    patch = np.full((70, 110, 3), 40, dtype=np.uint8)
    patch[10:60, 10:100] = (30, 30, 180)  # red-ish body (BGR)
    patch[55:70, 20:40] = 20
    patch[55:70, 70:90] = 20
    return patch


def make_clip(out: Path, *, label: str, fps: int = 10, seconds: int = 12) -> Path:
    try:
        import cv2
    except Exception as exc:  # pragma: no cover
        raise SystemExit(f"OpenCV required to write clips: {exc}") from exc

    out.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))
    n = fps * seconds
    rate = 272.50  # PKR/litre — fixed for the clip
    final_litres = 6.0
    final_amount = round(final_litres * rate, 2)

    for i in range(n):
        t = i / n
        frame = _bg(label)

        # Vehicle drives in, settles at the pump (~x=430) mid-clip, then leaves.
        if t < 0.25:
            vx = int(-120 + t / 0.25 * 550)
        elif t < 0.75:
            vx = 430
        else:
            vx = int(430 + (t - 0.75) / 0.25 * 700)
        _paste(frame, _vehicle_patch(t), vx, int(H * 0.52))

        # Meter: idle → counts up during the settled window → holds (sale settled).
        if t < 0.30:
            litres, amount = 0.0, 0.0
        elif t < 0.65:
            frac = (t - 0.30) / 0.35
            litres = round(final_litres * frac, 2)
            amount = round(litres * rate, 2)
        else:
            litres, amount = final_litres, final_amount
        _paste(frame, _meter_patch(amount, litres, rate, label), _METER_X, _METER_Y)

        writer.write(frame)

    writer.release()

    # Sidecar: authoritative ROIs + ground truth for deterministic offline tests.
    sidecar = out.with_suffix(".json")
    sidecar.write_text(
        json.dumps(
            {
                "synthetic": True,
                "label": label,
                "frame": {"width": W, "height": H},
                "fps": fps,
                "seconds": seconds,
                "meter_rois": meter_rois(),
                "field_digits": _FIELD_DIGITS,
                "decimals": 2,
                "ground_truth": {"amount": final_amount, "litres": final_litres, "rate": rate},
            },
            indent=2,
        )
    )
    log.info(
        "fixture_written",
        extra={"context": {"path": str(out), "sidecar": str(sidecar), "label": label, "frames": n}},
    )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate synthetic demo clips.")
    parser.add_argument("--label", choices=["day", "night"], default="day")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--seconds", type=int, default=12)
    args = parser.parse_args(argv)

    setup_logging(level="INFO", json_output=False)
    path = make_clip(args.out, label=args.label, fps=args.fps, seconds=args.seconds)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
