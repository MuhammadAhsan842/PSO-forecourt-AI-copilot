"""Synthetic 7-seg augmentation for CNN bootstrap (spec §6 training strategy).

Real fills stay the hold-out. These images are for training/bootstrap only.
"""

from __future__ import annotations

import numpy as np

from src.ocr.seven_seg import render_seven_seg


def augment_digit(
    img: np.ndarray,
    *,
    blur: float = 0.0,
    glare: float = 0.0,
    brightness: float = 1.0,
    tilt_deg: float = 0.0,
) -> np.ndarray:
    out = img.astype(np.float32) * float(brightness)
    out = np.clip(out, 0, 255)
    if blur > 0.4:
        import cv2

        k = int(max(3, round(blur) * 2 + 1))
        if k % 2 == 0:
            k += 1
        out = cv2.GaussianBlur(out, (k, k), blur)
    if abs(tilt_deg) > 0.2:
        import cv2

        h, w = out.shape[:2]
        m = cv2.getRotationMatrix2D((w / 2, h / 2), tilt_deg, 1.0)
        out = cv2.warpAffine(out, m, (w, h), borderValue=(18, 18, 18))
    if glare > 0:
        h, w = out.shape[:2]
        yy, xx = np.ogrid[:h, :w]
        blob = np.exp(-((xx - w * 0.7) ** 2 + (yy - h * 0.3) ** 2) / (2 * (w * 0.2) ** 2))
        out = np.clip(out + glare * 255.0 * blob[..., None], 0, 255)
    return out.astype(np.uint8)


def synthetic_bank(*, cell_w: int = 40, cell_h: int = 72) -> list[tuple[str, np.ndarray]]:
    """Digits 0–9 plus blank and a half-lit transition, with a few corruptions."""
    out: list[tuple[str, np.ndarray]] = []
    for d in "0123456789":
        base = render_seven_seg(d, cell_w=cell_w, cell_h=cell_h, vmargin=2)
        out.append((d, base))
        out.append((d, augment_digit(base, blur=1.2, brightness=0.85)))
        out.append((d, augment_digit(base, glare=0.35, tilt_deg=3.0)))
    blank = np.full((cell_h + 4, cell_w, 3), 18, dtype=np.uint8)
    out.append(("blank", blank))
    a = render_seven_seg("8", cell_w=cell_w, cell_h=cell_h, vmargin=2)
    b = render_seven_seg("0", cell_w=cell_w, cell_h=cell_h, vmargin=2)
    trans = ((a.astype(np.float32) + b.astype(np.float32)) / 2).astype(np.uint8)
    out.append(("transitioning", trans))
    return out
