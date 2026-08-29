"""Bezel registration — phase-correlation shift onto a template crop."""

from __future__ import annotations

import numpy as np


def _gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return img.astype(np.float32)
    return (0.114 * img[..., 0] + 0.587 * img[..., 1] + 0.299 * img[..., 2]).astype(np.float32)


def register_roi(
    roi: np.ndarray,
    template: np.ndarray | None,
) -> tuple[np.ndarray, float, float, float]:
    """Return ``(aligned, dx, dy, response)``. Identity if no template."""
    if template is None or roi.size == 0 or template.size == 0:
        return roi, 0.0, 0.0, 1.0
    if roi.shape[:2] != template.shape[:2]:
        return roi, 0.0, 0.0, 0.0
    import cv2

    a = _gray(roi)
    b = _gray(template)
    (dx, dy), response = cv2.phaseCorrelate(b, a)
    h, w = roi.shape[:2]
    m = np.float32([[1, 0, dx], [0, 1, dy]])
    aligned = cv2.warpAffine(roi, m, (w, h), flags=cv2.INTER_LINEAR)
    return aligned, float(dx), float(dy), float(response)
