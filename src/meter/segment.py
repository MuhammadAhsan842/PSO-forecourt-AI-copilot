"""Split a meter field ROI into per-digit cells (fixed even split)."""

from __future__ import annotations

import numpy as np


def cell_bounds(width: int, num_digits: int) -> list[tuple[int, int]]:
    n = max(1, int(num_digits))
    edges = np.linspace(0, width, n + 1).astype(int)
    return [(int(edges[i]), int(edges[i + 1])) for i in range(n)]


def split_cells(roi: np.ndarray, num_digits: int) -> list[np.ndarray]:
    if roi.size == 0:
        return []
    _, w = roi.shape[:2]
    return [roi[:, x0:x1] for x0, x1 in cell_bounds(w, num_digits) if x1 > x0]
