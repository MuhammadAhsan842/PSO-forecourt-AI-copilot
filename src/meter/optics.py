"""Phase 0 optics measurements — no digit reading.

Honest scores only: pixel size, sharpness, glare, contrast, a coarse display-type
guess. The ≥600×300 PASS/FAIL gate is computed here so a site report cannot
hand-wave a 220×110 crop into a reader build.
"""

from __future__ import annotations

from typing import Any

import numpy as np

GATE_MIN_W = 600
GATE_MIN_H = 300


def crop_roi(frame: np.ndarray, x: int, y: int, w: int, h: int) -> np.ndarray:
    fh, fw = frame.shape[:2]
    x = max(0, min(int(x), fw - 1))
    y = max(0, min(int(y), fh - 1))
    w = max(1, min(int(w), fw - x))
    h = max(1, min(int(h), fh - y))
    return frame[y : y + h, x : x + w]


def _gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return img
    import cv2

    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def sharpness_laplacian(roi: np.ndarray) -> float:
    import cv2

    g = _gray(roi)
    return float(cv2.Laplacian(g, cv2.CV_64F).var())


def glare_stats(roi: np.ndarray) -> dict[str, float]:
    g = _gray(roi).astype(np.float64)
    if g.size == 0:
        return {"mean": 0.0, "highlight_frac": 0.0, "p95": 0.0}
    return {
        "mean": float(g.mean()),
        "highlight_frac": float((g >= 240).mean()),
        "p95": float(np.percentile(g, 95)),
    }


def contrast_score(roi: np.ndarray) -> float:
    """Michelson-ish contrast from p5/p95. 0 = flat, ~1 = full swing."""
    g = _gray(roi).astype(np.float64)
    if g.size == 0:
        return 0.0
    lo, hi = float(np.percentile(g, 5)), float(np.percentile(g, 95))
    denom = hi + lo
    if denom <= 1e-6:
        return 0.0
    return float((hi - lo) / denom)


def guess_display_type(roi: np.ndarray) -> str:
    """Coarse heuristic — not a classifier. Human survey still wins.

    - graphic_lcd: strong blue-ish backlight, low edge density
    - seven_segment: strong axis-aligned edges (segment bars)
    - mechanical_wheel: medium texture, weaker vertical bars
    - unknown: everything else
    """
    if roi.size == 0 or min(roi.shape[:2]) < 8:
        return "unknown"
    import cv2

    g = _gray(roi)
    b_mean = float(roi[:, :, 0].mean()) if roi.ndim == 3 else 0.0
    g_mean = float(roi[:, :, 1].mean()) if roi.ndim == 3 else float(g.mean())
    r_mean = float(roi[:, :, 2].mean()) if roi.ndim == 3 else 0.0
    edges = cv2.Canny(g, 40, 120)
    edge_frac = float(edges.mean() / 255.0)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    axis_ratio = float((np.abs(gx).mean() + 1e-6) / (np.abs(gy).mean() + 1e-6))

    if roi.ndim == 3 and b_mean > r_mean + 25 and b_mean > g_mean + 10 and edge_frac < 0.08:
        return "graphic_lcd"
    if edge_frac > 0.06 and 0.6 < axis_ratio < 1.7:
        return "seven_segment"
    if 0.02 < edge_frac < 0.08:
        return "mechanical_wheel"
    return "unknown"


def optics_report(roi: np.ndarray) -> dict[str, Any]:
    h, w = roi.shape[:2]
    pass_px = w >= GATE_MIN_W and h >= GATE_MIN_H
    glare = glare_stats(roi)
    sharp = sharpness_laplacian(roi)
    contrast = contrast_score(roi)
    return {
        "roi_width": w,
        "roi_height": h,
        "gate_min_wh": [GATE_MIN_W, GATE_MIN_H],
        "pass_px": pass_px,
        "sharpness_laplacian": round(sharp, 1),
        "glare": {k: round(v, 4) for k, v in glare.items()},
        "contrast": round(contrast, 4),
        "display_guess": guess_display_type(roi),
        "gate_reason": (
            "PASS pixel gate"
            if pass_px
            else (
                f"FAIL pixel gate: {w}x{h} < {GATE_MIN_W}x{GATE_MIN_H}. "
                "Do not build the reader on this crop — optical zoom or a "
                "dedicated meter camera is required."
            )
        ),
    }
