"""Label digit cells static vs rolling vs blank from frame-to-frame change."""

from __future__ import annotations

import numpy as np

BLANK = "blank"
STATIC = "static"
ROLLING = "rolling"


def _gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return img.astype(np.float32)
    return (0.114 * img[..., 0] + 0.587 * img[..., 1] + 0.299 * img[..., 2]).astype(np.float32)


class ChangeRateLabeler:
    def __init__(self, *, roll_mae: float = 14.0, blank_mean: float = 18.0):
        self.roll_mae = roll_mae
        self.blank_mean = blank_mean
        self._prev: list[np.ndarray] | None = None

    def label(self, cells: list[np.ndarray]) -> list[str]:
        out: list[str] = []
        prev = self._prev
        stored: list[np.ndarray] = []
        for i, cell in enumerate(cells):
            g = _gray(cell)
            stored.append(g)
            if float(g.mean()) < self.blank_mean:
                out.append(BLANK)
                continue
            if prev is None or i >= len(prev) or prev[i].shape != g.shape:
                out.append(STATIC)
                continue
            mae = float(np.mean(np.abs(g - prev[i])))
            out.append(ROLLING if mae >= self.roll_mae else STATIC)
        self._prev = stored
        return out

    def reset(self) -> None:
        self._prev = None
